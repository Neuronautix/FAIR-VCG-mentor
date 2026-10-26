# VCG Proof-of-Concept — Rodent Repeat-Dose Toxicology

This folder is a self-contained proof-of-concept for the **Virtual Control Group
(VCG)** pipeline. It synthesizes a realistic *historical concurrent-control* pool
for a rodent repeat-dose toxicology study, runs the **real backend pipeline**
(`backend/vcg/vcg_engine.run_vcg_pipeline`) end-to-end on it, and quantifies how
faithfully the generated virtual controls reproduce the real control group.

> **What this demonstrates:** for a 6-endpoint preclinical toxicology control
> group (N=24), the Gaussian-copula bootstrap reproduces each endpoint's
> marginal distribution *and* the inter-endpoint correlation structure closely
> enough (reliability **0.935 / 1.0**) to support partial replacement of
> concurrent controls — the core use case for VCGs under the 3Rs (Reduction).

No FastAPI server, no LLM API key, and no network access are required.

---

## Files

| File | Role |
|------|------|
| `generate_dataset.py` | Synthesizes the historical control pool from a **known** ground-truth structure |
| `run_poc.py` | Drives the real four-agent VCG pipeline and writes the artifacts below |
| `../../test_data/tox_historical_controls.csv` | The generated input dataset (N=24 Vehicle controls) |
| `outputs/vcg_synthetic_controls.csv` | The VCG-generated synthetic control cohort (N=30) |
| `outputs/vcg_report.md` | The pipeline's Markdown statistical report |
| `outputs/poc_results.json` | Machine-readable summary: scores, balance, fidelity, correlation recovery |

## Reproduce

```bash
cd FAIR-VCG-mentor
python docs/vcg_poc/generate_dataset.py   # writes test_data/tox_historical_controls.csv
python docs/vcg_poc/run_poc.py            # runs the pipeline, writes docs/vcg_poc/outputs/
```

Both scripts are fully deterministic (dataset seed `20240611`, VCG seed `42`).

---

## The dataset

`tox_historical_controls.csv` mimics a historical-control database that a lab
accumulates across studies — 24 Vehicle (dose 0 mg/kg) animals drawn from three
historical batches (`HC-2023-04`, `HC-2023-09`, `HC-2024-02`), both sexes, mostly
Sprague-Dawley with a minority of Wistar.

| Role | Columns |
|------|---------|
| **Subject ID** | `animal_id` |
| **Treatment** (control = `Vehicle`) | `group`, `dose_mg_kg` |
| **Outcomes / endpoints** | `body_weight_end_g`, `liver_weight_g`, `kidney_weight_g`, `alt_u_l`, `ast_u_l`, `creatinine_umol_l` |
| **Covariates** | `sex`, `strain` |
| **Context** | `study_id`, `age_weeks`, `operator`, `collection_date` |

Values are anchored to the Vehicle controls already in
`test_data/FAIR-VCG_example_data.csv` (≈310 g males / ≈205 g females, ALT ≈48 U/L,
AST ≈65 U/L, creatinine ≈55 µmol/L).

**Ground-truth structure baked into the data** (so the PoC can check recovery):

1. **Sex dimorphism** — males ≈50% heavier than females; organ weights scale.
2. **Organ-size scaling** — liver & kidney weights are driven by terminal body
   weight (pooled Spearman ρ ≈ 0.84–0.91).
3. **Hepatic co-movement** — AST is regressed on ALT, so the two transaminases
   move together (ρ ≈ 0.68). This is exactly the kind of structure naive
   per-column sampling destroys and the copula is meant to keep.

---

## Pipeline run

`run_poc.py` rebuilds the same `session` object the app constructs on
`POST /api/upload` (profiling the CSV with `csv_profiler.profile_csv` to get
`session["df"]` and `session["columns"]`), configures `ColumnRoles` + `VCGConfig`
(method `bootstrap`, `n_synthetic=30`, `seed=42`), and calls the unmodified
`run_vcg_pipeline`. The four agents run in sequence:

`DataIngestionAgent` → `DataStandardizationAgent` → `BootstrapVCGAgent` → `StatsAgent`

```
pipeline status: done
method: bootstrap   real N=24  ->  VCG N=30
reliability score: 0.935
```

### Result 1 — marginal fidelity (per endpoint)

| Endpoint | Real mean ± SD | VCG mean ± SD | Δ mean | Cohen's d | KS p | Verdict |
|----------|---------------:|--------------:|-------:|----------:|-----:|---------|
| body_weight_end_g | 254.0 ± 52.1 | 265.4 ± 51.4 | +4.5% | −0.22 | 0.15 | Acceptable |
| liver_weight_g | 8.79 ± 1.67 | 8.99 ± 1.61 | +2.2% | −0.12 | 0.25 | Good |
| kidney_weight_g | 1.602 ± 0.294 | 1.642 ± 0.267 | +2.5% | −0.14 | 0.80 | Excellent |
| alt_u_l | 44.4 ± 5.0 | 43.9 ± 4.2 | −1.1% | +0.10 | 0.92 | Excellent |
| ast_u_l | 61.8 ± 10.1 | 61.4 ± 7.6 | −0.7% | +0.05 | 0.59 | Excellent |
| creatinine_umol_l | 56.0 ± 7.7 | 55.0 ± 6.2 | −1.8% | +0.15 | 0.75 | Excellent |

Every endpoint's mean is within **±4.5%**, every Cohen's d is small
(|d| ≤ 0.22), and **no** Kolmogorov-Smirnov test is significant — i.e. the real
and virtual controls are statistically indistinguishable on each marginal. The
marginals were auto-fitted as **log-normal** (body/liver/kidney weights) and
**gamma** (ALT/AST/creatinine).

### Result 2 — correlation-structure recovery

Mean absolute Spearman-ρ error across all 15 endpoint pairs: **0.106**.
The structurally meaningful blocks are preserved:

| Relationship | Real ρ | VCG ρ |
|--------------|-------:|------:|
| body ↔ liver | 0.91 | 0.92 |
| body ↔ kidney | 0.88 | 0.89 |
| liver ↔ kidney | 0.84 | 0.89 |
| ALT ↔ AST (hepatic) | 0.68 | 0.76 |
| organ ↔ creatinine | 0.58–0.70 | 0.57–0.73 |

The largest single error (max |Δρ| = 0.32) is on a **near-zero** pair
(liver ↔ ALT: real −0.24 → VCG +0.08): a weak, noise-level correlation the
copula does not lock onto. No load-bearing relationship is lost — the strong
organ-size and transaminase blocks come through intact, which is the point of
using a copula bootstrap over independent per-column sampling.

---

## Caveats

- This is a **methodological demonstration on synthetic data**, not a validated
  control-replacement claim. As the pipeline's own report states, VCGs are an
  aid — not a substitute for randomised controls — and must be reviewed by a
  qualified statistician before any regulatory or publication use.
- N=24 is comfortably above the N≥15 bootstrap threshold but still small; the
  copula recovers strong correlations well and weak ones noisily.
- The ground truth here is *known by construction*. On real data, fidelity
  scores describe agreement between the VCG and the supplied control sample, not
  agreement with an underlying population.
