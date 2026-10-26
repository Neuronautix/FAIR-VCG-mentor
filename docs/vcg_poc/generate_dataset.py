"""
Synthesize a realistic *historical concurrent-control* dataset for a rodent
repeat-dose toxicology study, for use as the input to the VCG proof-of-concept.

This is the "real" control pool that a lab would have accumulated. We generate it
from a KNOWN ground-truth structure so the PoC can check whether the VCG pipeline
recovers that structure:

  * sex dimorphism      — males are ~50% heavier than females; organ weights scale
  * organ-size scaling  — liver & kidney weights are driven by terminal body weight
  * hepatic co-movement — ALT and AST are positively correlated (shared liver signal)

Endpoints (outcomes):
    body_weight_end_g, liver_weight_g, kidney_weight_g, alt_u_l, ast_u_l, creatinine_umol_l
Covariates:
    sex, strain

The numbers are anchored to the Vehicle controls in test_data/FAIR-VCG_example_data.csv
(Sprague-Dawley, ~310 g males / ~205 g females, ALT ~48 U/L, AST ~65 U/L, etc.).

Run:  python docs/vcg_poc/generate_dataset.py
Out:  test_data/tox_historical_controls.csv  (N=24 Vehicle controls)
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd

SEED = 20240611
N_PER_SEX = 12          # 12 males + 12 females = 24 control animals
OUT = os.path.join(
    os.path.dirname(__file__), "..", "..", "test_data", "tox_historical_controls.csv"
)

# ── Ground-truth parameters per sex ──────────────────────────────────────────
# Each tuple is (mean, sd) on the natural scale for the seed endpoint.
SEX_PARAMS = {
    "Male": {
        "bw_mean": 312.0, "bw_sd": 18.0,      # terminal body weight (g)
        "liver_per_bw": 0.0345, "liver_sd": 0.45,   # liver = liver_per_bw * bw + noise
        "kidney_per_bw": 0.00610, "kidney_sd": 0.09,
        "alt_mean": 48.0, "alt_sd": 6.5,      # ALT (U/L) seed; AST built off ALT
        "ast_intercept": 18.0, "ast_slope": 1.05, "ast_sd": 9.0,
        "creat_mean": 60.0, "creat_sd": 6.0,  # creatinine (umol/L), ~independent
    },
    "Female": {
        "bw_mean": 207.0, "bw_sd": 14.0,
        "liver_per_bw": 0.0350, "liver_sd": 0.32,
        "kidney_per_bw": 0.00640, "kidney_sd": 0.07,
        "alt_mean": 45.0, "alt_sd": 6.0,
        "ast_intercept": 16.0, "ast_slope": 1.05, "ast_sd": 9.0,
        "creat_mean": 50.0, "creat_sd": 6.0,
    },
}

# Historical controls span several studies / operators / dates (typical of a
# real historical-control database). These are covariate/context, not outcomes.
STUDIES = [
    ("HC-2023-04", "J.Martin", "2023-04-18"),
    ("HC-2023-09", "S.Lee",    "2023-09-12"),
    ("HC-2024-02", "K.Patel",  "2024-02-27"),
]


def _gen_sex(rng: np.random.Generator, sex: str, n: int) -> pd.DataFrame:
    p = SEX_PARAMS[sex]
    # Body weight drives organ weights (positive structural correlation).
    bw = rng.normal(p["bw_mean"], p["bw_sd"], n)
    liver = p["liver_per_bw"] * bw + rng.normal(0, p["liver_sd"], n)
    kidney = p["kidney_per_bw"] * bw + rng.normal(0, p["kidney_sd"], n)
    # ALT seed, AST regressed on ALT -> the two move together (hepatic signal).
    alt = rng.normal(p["alt_mean"], p["alt_sd"], n)
    ast = p["ast_intercept"] + p["ast_slope"] * alt + rng.normal(0, p["ast_sd"], n)
    creat = rng.normal(p["creat_mean"], p["creat_sd"], n)
    return pd.DataFrame(
        {
            "sex": sex,
            "body_weight_end_g": np.round(bw, 1),
            "liver_weight_g": np.round(np.clip(liver, 3, None), 2),
            "kidney_weight_g": np.round(np.clip(kidney, 0.5, None), 3),
            "alt_u_l": np.round(np.clip(alt, 5, None), 1),
            "ast_u_l": np.round(np.clip(ast, 5, None), 1),
            "creatinine_umol_l": np.round(np.clip(creat, 5, None), 1),
        }
    )


def main() -> None:
    rng = np.random.default_rng(SEED)
    males = _gen_sex(rng, "Male", N_PER_SEX)
    females = _gen_sex(rng, "Female", N_PER_SEX)
    df = pd.concat([males, females], ignore_index=True)

    # Interleave sexes so studies contain a mix, then assign context columns.
    df = df.sample(frac=1.0, random_state=SEED).reset_index(drop=True)
    n = len(df)
    df.insert(0, "animal_id", [f"HC-{i+1:03d}" for i in range(n)])
    df.insert(1, "group", "Vehicle")          # all historical controls are Vehicle
    df.insert(2, "dose_mg_kg", 0)
    # ~85% Sprague-Dawley, ~15% Wistar to exercise the strain covariate.
    strains = rng.choice(["Sprague-Dawley", "Wistar"], size=n, p=[0.83, 0.17])
    df.insert(4, "strain", strains)
    df.insert(5, "age_weeks", np.round(rng.normal(8.4, 0.45, n), 1))

    study_idx = rng.integers(0, len(STUDIES), size=n)
    df["study_id"] = [STUDIES[i][0] for i in study_idx]
    df["operator"] = [STUDIES[i][1] for i in study_idx]
    df["collection_date"] = [STUDIES[i][2] for i in study_idx]

    cols = [
        "animal_id", "study_id", "sex", "strain", "age_weeks",
        "group", "dose_mg_kg",
        "body_weight_end_g", "liver_weight_g", "kidney_weight_g",
        "alt_u_l", "ast_u_l", "creatinine_umol_l",
        "operator", "collection_date",
    ]
    df = df[cols]

    out = os.path.abspath(OUT)
    df.to_csv(out, index=False)
    print(f"Wrote {len(df)} historical Vehicle controls -> {out}")

    # Report the ground-truth correlations we baked in, for the writeup.
    num = ["body_weight_end_g", "liver_weight_g", "kidney_weight_g",
           "alt_u_l", "ast_u_l", "creatinine_umol_l"]
    print("\nPooled Spearman correlation (ground truth in the data):")
    print(df[num].corr(method="spearman").round(2).to_string())


if __name__ == "__main__":
    main()
