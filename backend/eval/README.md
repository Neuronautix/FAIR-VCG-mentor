# Masked-metadata validation harness

Grant **Milestone C**. Quantifies how well a metadata predictor recovers column
**semantic types** from datasets whose metadata signal has been *masked*, and
emits a provider **scorecard** (accuracy · hallucination rate · confidence
calibration). It lets us compare the deterministic baseline against cloud and
local LLMs (Gemma / APERTUS) toward the grant's ~90 % accuracy target.

## Why "masked"

A fresh CSV carries no human-authored metadata, so the meaningful mask is over
the *signal a predictor may use*:

| Level | Headers | Tests |
| --- | --- | --- |
| `raw` | kept | name + value inference (a normal upload) |
| `blind` | replaced with `var_1…` | **value-only** inference — exposes reliance on column-name patterns |

The gap between `raw` and `blind` accuracy is the key robustness signal: a
predictor that collapses under `blind` is just pattern-matching names.

## Run it

```bash
cd backend
# Deterministic baseline (offline, no model needed):
python -m eval.run_eval --predictor deterministic

# Against the configured LLM provider (Anthropic, or a local LM Studio model
# via LLM_PROVIDER=openai / LLM_BASE_URL / LLM_MODEL):
python -m eval.run_eval --predictor llm --format markdown --out scorecard.md
```

## Baseline (rule-based profiler)

The deterministic profiler scores ~100 % with real headers but drops to ~55 %
under `blind` masking (and never hallucinates a type). Closing that `blind` gap
with a grounded local LLM is the substance of Milestones A + C.

## Layout

| File | Role |
| --- | --- |
| `datasets.py` | eval dataset registry + ground-truth semantic types (canonical source) |
| `masking.py` | `raw` / `blind` masking, returns the header → original name map |
| `predictors.py` | `DeterministicPredictor`, `LLMPredictor` (provider-agnostic), `CallablePredictor` (tests) |
| `scoring.py` | per-column results + accuracy / hallucination / calibration metrics |
| `scorecard.py` | `ScoreCard` aggregation + JSON / Markdown rendering |
| `run_eval.py` | `evaluate(predictor, …)` orchestration + CLI |

Adding a predictor = implement `predict(columns) -> dict[name, Prediction]` and
pass it to `evaluate(...)`. Tests live in `backend/tests/test_eval_harness.py`.
