import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional


class DataStandardizationAgent:
    """Cleans and standardises the control group subset before VCG generation."""

    def run(
        self,
        control_df: pd.DataFrame,
        columns: List[Dict],
        outcome_cols: List[str],
        covariate_cols: List[str],
    ) -> Dict[str, Any]:
        """
        Returns {
            "standardized_df": pd.DataFrame,
            "log": List[str],       # what was changed
            "quality_score": float, # 0-1
            "warnings": List[str],
        }

        Steps applied (in order):
        1. Unit harmonisation: for each outcome column, check if unit_guess exists in the
           column dict. Log it. (Phase 1: just log, no conversion.)
        2. Missing value imputation: numeric columns -> median; categorical columns -> mode.
           Log each imputation.
        3. Outlier flagging: for each numeric outcome col, values outside
           mean +/- 3*std are flagged in a new column "{col}_outlier_flag" (bool).
           Do NOT remove outliers. Log count of flagged values.
        4. Categorical normalisation: for each covariate column of dtype object,
           strip whitespace and lowercase all values. Log changes.

        quality_score = 1.0 - 0.1 * (total_missing_before / (n_rows * n_outcome_cols))
        clipped to [0, 1].
        """
        log: List[str] = []
        warnings: List[str] = []

        if control_df.empty:
            return {
                "standardized_df": control_df.copy(),
                "log": ["Input DataFrame is empty — nothing to standardize."],
                "quality_score": 0.0,
                "warnings": ["Control group DataFrame is empty."],
            }

        df = control_df.copy()
        n_rows = len(df)
        n_outcome_cols = max(len(outcome_cols), 1)

        # Build a lookup from column name to column metadata dict
        col_meta: Dict[str, Dict] = {c["name"]: c for c in columns}

        # ── Step 1: Unit harmonisation (log only) ────────────────────────────
        for col in outcome_cols:
            if col not in df.columns:
                continue
            meta = col_meta.get(col, {})
            unit = meta.get("user_unit") or meta.get("unit_guess")
            if unit:
                log.append(f"Unit harmonisation: '{col}' reported unit is '{unit}' (logged, no conversion applied).")
            else:
                log.append(f"Unit harmonisation: '{col}' has no unit information available.")

        # ── Step 2: Missing value imputation ─────────────────────────────────
        total_missing_before = 0
        all_target_cols = list(set(outcome_cols + covariate_cols))

        for col in all_target_cols:
            if col not in df.columns:
                continue

            missing_mask = df[col].isna()
            n_missing = int(missing_mask.sum())
            total_missing_before += n_missing

            if n_missing == 0:
                continue

            # Try numeric imputation
            numeric = pd.to_numeric(df[col], errors="coerce")
            if numeric.notna().sum() > 0 and numeric.notna().mean() > 0.5:
                median_val = numeric.median()
                df[col] = df[col].where(~missing_mask, other=median_val)
                log.append(
                    f"Imputation: '{col}' — {n_missing} missing value(s) replaced with median ({median_val:.4g})."
                )
            else:
                # Categorical imputation: mode
                non_null = df[col].dropna()
                m = non_null.mode()
                if len(non_null) > 0 and len(m) > 0:
                    mode_val = m.iloc[0]
                    df[col] = df[col].fillna(mode_val)
                    log.append(
                        f"Imputation: '{col}' — {n_missing} missing value(s) replaced with mode ('{mode_val}')."
                    )
                else:
                    log.append(
                        f"Imputation: '{col}' — {n_missing} missing value(s) but no non-null values to impute from."
                    )
                    warnings.append(f"Column '{col}' is entirely missing; cannot impute.")

        # ── Step 3: Outlier flagging ──────────────────────────────────────────
        for col in outcome_cols:
            if col not in df.columns:
                continue

            numeric = pd.to_numeric(df[col], errors="coerce")
            valid = numeric.dropna()

            if len(valid) < 3:
                continue

            mean_val = valid.mean()
            std_val = valid.std(ddof=1)

            if std_val == 0 or np.isnan(std_val):
                continue

            lower = mean_val - 3 * std_val
            upper = mean_val + 3 * std_val
            outlier_mask = (numeric < lower) | (numeric > upper)
            n_outliers = int(outlier_mask.sum())

            flag_col = f"{col}_outlier_flag"
            df[flag_col] = outlier_mask.fillna(False)

            if n_outliers > 0:
                log.append(
                    f"Outlier flagging: '{col}' — {n_outliers} value(s) outside mean ± 3SD "
                    f"([{lower:.4g}, {upper:.4g}]) flagged in '{flag_col}' (not removed)."
                )
                warnings.append(
                    f"Column '{col}' has {n_outliers} outlier(s) flagged. Review before VCG generation."
                )
            else:
                log.append(f"Outlier flagging: '{col}' — no outliers detected outside mean ± 3SD.")

        # ── Step 4: Categorical normalisation ────────────────────────────────
        for col in covariate_cols:
            if col not in df.columns:
                continue

            if df[col].dtype != object:
                continue

            original = df[col].copy()
            df[col] = df[col].apply(
                lambda x: str(x).strip().lower() if pd.notna(x) else x
            )
            changed = (df[col] != original).sum()
            if changed > 0:
                log.append(
                    f"Categorical normalisation: '{col}' — {changed} value(s) stripped and lowercased."
                )

        # ── Quality score ─────────────────────────────────────────────────────
        quality_score = max(
            0.0,
            min(
                1.0,
                1.0 - 0.1 * (total_missing_before / (n_rows * n_outcome_cols)),
            ),
        )

        return {
            "standardized_df": df,
            "log": log,
            "quality_score": round(quality_score, 4),
            "warnings": warnings,
        }
