# Virtual Control Group — Statistical Report

> ⚠ **DISCLAIMER**: Virtual control groups are a methodological aid — not a substitute for
> randomised experimental controls. Results should be interpreted with caution and reviewed
> by a qualified statistician before use in regulatory submissions or publications.

---

## 1. Study Context

| Field | Value |
|---|---|
| Research domain | toxicology |
| Study type | dose_response |
| Primary entity | entity |
| Control label | Vehicle |

---

## 2. Data Summary

- **Real control subjects**: N = 24
- **Virtual control subjects**: N = 30
- **Endpoints modelled**: `body_weight_end_g`, `liver_weight_g`, `kidney_weight_g`, `alt_u_l`, `ast_u_l`, `creatinine_umol_l`
- **Covariates balanced**: `sex`, `strain`

---

## 3. Generation Method

**Method used**: `bootstrap`

Parametric bootstrap with Gaussian copula. Marginal distributions were fitted per endpoint (Normal, Log-Normal, or Gamma selected via Shapiro-Wilk). The Gaussian copula preserves Spearman rank correlations between endpoints. Appropriate for N≥15.

**Random seed**: 42 (fixed for reproducibility)

---

## 4. Covariate Balance

SMD < 0.1 = Excellent | 0.1–0.25 = Acceptable | > 0.25 = Poor

| Covariate | SMD | Assessment |
|---|---|---|
| sex | 0.134 | Acceptable |
| strain | 0.201 | Acceptable |

---

## 5. Outcome Distribution Comparison

| Endpoint | Mean±SD (Real) | Mean±SD (VCG) | KS p-value | Cohen's d | Interpretation |
|---|---|---|---|---|---|
| body_weight_end_g | 254 ± 52.1 | 265 ± 51.4 | 0.150 | -0.219 | small |
| liver_weight_g | 8.79 ± 1.67 | 8.99 ± 1.61 | 0.254 | -0.120 | negligible |
| kidney_weight_g | 1.6 ± 0.294 | 1.64 ± 0.267 | 0.799 | -0.144 | negligible |
| alt_u_l | 44.4 ± 5.04 | 43.9 ± 4.2 | 0.916 | 0.104 | negligible |
| ast_u_l | 61.8 ± 10.1 | 61.4 ± 7.59 | 0.593 | 0.047 | negligible |
| creatinine_umol_l | 56 ± 7.66 | 55 ± 6.16 | 0.747 | 0.146 | negligible |

---

## 6. Statistical Power

| Endpoint | Achieved Power | N for 80% Power |
|---|---|---|
| body_weight_end_g | 0.12 | 328 |
| liver_weight_g | 0.07 | 1099 |
| kidney_weight_g | 0.08 | 763 |
| alt_u_l | 0.06 | 1444 |
| ast_u_l | 0.05 | 7230 |
| creatinine_umol_l | 0.08 | 736 |

---

## 7. Reliability Assessment

**Overall reliability score**: 0.94 / 1.00 (HIGH)

The VCG closely replicates the observed control distribution.

---

## 8. Warnings

_None._

---

## 9. Limitations

- VCG is derived from N=24 real control subjects; conclusions are limited by this sample size.
- Marginal distributions are fitted independently; complex multivariate relationships beyond pairwise correlations may not be fully captured (Phase 1 bootstrap) or at all (synthetic method).
- The generated dataset is intended to supplement, not replace, concurrent controls in primary efficacy analyses.
- External validity depends on the historical data being representative of the current experimental conditions (species, age, housing, handling).

---

## 10. Reproducibility

| Parameter | Value |
|---|---|
| Generated | 2026-06-24 07:28:46 UTC |
| scipy version | 1.17.1 |
| Method | bootstrap |
| Seed | 42 |
| n_real | 24 |
| n_vcg | 30 |

---

## 11. 3Rs Justification Template

> Virtual controls were generated from **24 historical Vehicle subjects** using
> **bootstrap sampling** (seed=42). The VCG demonstrates **high** distributional
> similarity to the source population (KS tests: p > 0.05 for 6/6 endpoints;
> mean covariate SMD = 0.167). This approach supports reduction of up to **30 animals**
> in concurrent control groups, consistent with the 3Rs principles (Russell & Burch, 1959) and
> current guidance on the use of historical control data in non-clinical studies.
