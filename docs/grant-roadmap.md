# FAIR-VCG Mentor — Local-LLM & Grant Compatibility Roadmap

Status: **living document** · Context: Swiss 3RCC Support grant (Neuronautix / UNIL), 12 months, start 2026-10-01.

This roadmap maps the grant's milestones onto concrete engineering work in this
repository. It is the planning counterpart to `CLAUDE.md` (which documents the
system as-built).

---

## 1. Objective

Make FAIR-VCG Mentor run **fully on a locally-hosted LLM** (APERTUS / Gemma via
LM Studio's OpenAI-compatible API) with **no commercial or external API
dependency**, ground metadata reasoning in a **preclinical knowledge graph**,
and prove **~90 % accuracy** through a **masked-metadata validation harness** —
culminating in a proof-of-concept Virtual Control Group (VCG) and a
dissemination package.

## 2. Starting point (codebase audit, 2026-06)

- **The tool is already ~90 % offline.** The only outbound network dependencies
  are **Anthropic** (the LLM, used at 10 call sites) and **CrossRef**
  (`doi_fetcher.py`, DOI lookup, user-triggered only). FAIR scoring, VCG
  generation, templates, exports, PDF *text* extraction (`pdfminer.six`), and
  SQLite sessions are all local. The schema.org / RO-Crate / OBO URIs in
  exports are reference strings, never fetched at runtime.
- **LLM coupling:** most calls funnel through `llm_service.call_haiku()` using
  Anthropic's *forced single-tool* pattern; **3 sites bypass it** with direct
  `anthropic.Anthropic()` calls — `llm_fair_scorer.py`, `paper_extractor.py`,
  `nts_analyzer.py`. Per-feature model env vars already exist
  (`PAPER_EXTRACTION_MODEL`, `FAIR_SCORER_MODEL`, …). PDFs are sent via
  Anthropic's native `document` blocks.
- **Grounding scaffold already exists** and is reused rather than rebuilt:
  `vocabulary.py` is a per-session controlled vocabulary injected as a cached
  system block (`schema_prompt_block`) with enum-constrained tool schemas; a
  HITL queue (`hitl.py`) dry-run-validates every suggestion; semantic-type
  inference (`csv_profiler.py` + `vcg/constants.py`) is benchmarked by
  `tests/column_inference_benchmark.py`.
- **Gaps to fill:** no provider abstraction, no local PDF→text path, no real
  knowledge graph (`uri_suggester.py` is template-only), no LLM-output /
  masked-metadata validation harness.

## 2b. Progress (live)

| Milestone | Status | Where |
|-----------|--------|-------|
| **B** — provider-agnostic LLM layer | ✅ merged | PR #15 (provider switch, structured-output local path, local PDF→text, `provider_info()`, CrossRef gated) |
| **B** — local deployment (docker `local-llm` profile, setup docs, live-endpoint smoke) | ✅ on branch | merged into `fair-vcg-complete-3r-grant` (`docker-compose.local-llm.yml`, `docs/local-llm-setup.md`, `backend/scripts/llm_smoke.py`) |
| **C** — masked-metadata validation harness + scorecard | ✅ merged | PR #16 (`backend/eval/`; current scorecard: deterministic 73.2% overall / 48.8% blind, KG 76.8% / 58.5% blind, 0% hallucination) |
| **A** — preclinical metadata knowledge graph + grounding | ✅ merged | PR #17 (`backend/knowledge/`, from the precliniverse schema; grounding + offline ontology IRIs) |
| **A↔C bridge** — KG-grounded eval predictor (quantifies blind-mode lift) | ✅ on branch | merged into `fair-vcg-complete-3r-grant` — **+50 pp blind-mode accuracy (0.25 → 0.75) on the synthetic set, 0% hallucination** |
| **D** — integration tests on academic datasets | 🛠 harness ready | headless end-to-end test `backend/tests/test_integration_pipeline.py` (profile → FAIR → VCG) on a synthetic placeholder; still blocked on an anonymised UNIL dataset + live local endpoint |
| **E** — proof-of-concept VCG report (one use case) | ✅ on branch | rodent-toxicology PoC `docs/vcg_poc/` (synthetic CSV + stats report + `poc_results.json`, reliability 0.935) |
| **F** — dissemination package | ✅ on branch | `backend/scripts/build_dissemination.py` bundles scorecards + VCG PoC + local-llm profile into `dist/dissemination/` (see §8) |

Legend: ✅ merged · ✅ on branch (in `fair-vcg-complete-3r-grant`, not yet in `main`) · 🔍 in review (open PR) · 🛠 in progress (branch) · ⏳ not started.

## 3. Decisions on record

| # | Decision | Choice |
|---|----------|--------|
| 1 | CrossRef / DOI lookup | Keep, but behind an explicit `ENABLE_ONLINE_ENRICHMENT` flag that is **OFF by default**. Local mode is fully offline; the feature still works when opted in. |
| 2 | Knowledge-graph scope | **Lightweight**: extend `vocabulary.py` into a SKOS/JSON-LD term graph + deterministic retriever, with optional external-ontology IRI references (UO/UCUM/NCBITaxon). No triplestore. |
| 3 | Local-model interface | Drive local models via **structured-output JSON-schema** (LM Studio `response_format`) built from existing tool `input_schema`s, with a tool-call fallback. More reliable on Gemma/APERTUS than tool-calling. |

## 4. Workstreams → milestones

### WS1 · Provider-agnostic LLM layer → **Milestone B** (critical, M2) — foundation
- `LLM_PROVIDER` switch (`anthropic` | `openai`) in `llm_service.py`; OpenAI-
  compatible client for LM Studio (`LLM_BASE_URL`, `LLM_MODEL`, optional
  `LLM_API_KEY`). `call_haiku()` keeps its signature and dict return, so all
  ten call sites are unchanged.
- Local path uses `response_format={"type":"json_schema", …}` from the tool's
  `input_schema`; drops Anthropic-only `cache_control`.
- Consolidate the 3 direct-SDK sites onto the wrapper → one provider seam.
- Generalize `llm_enabled()` + `/api/llm/status` to report provider, model, and
  configured state.

### WS2 · Local PDF / document handling → part of **Milestone B**
- Provider-conditional input: local models receive locally-extracted text
  (`pdfminer.six`); Anthropic keeps native PDF blocks. Centralized in
  `llm_service` so `paper_extractor` / `nts_analyzer` / `llm_vocab_discovery`
  need no change. Add context-window truncation (`LLM_MAX_DOC_CHARS`).

### WS3 · Preclinical metadata knowledge graph + grounding → **Milestone A** (M1)
- Versioned KG in `backend/knowledge/` reusing the vocabulary scaffold:
  controlled terms for semantic types, the ARRIVE/PREPARE/MNMS/NAMO/EQIPD field
  registries, units (→ UO/UCUM IRIs), species/strain/sex, with light
  relationships. **Grounding = retrieval-augmented injection**: a deterministic
  retriever selects the relevant subgraph per column and injects it via the
  existing cached-block path + enum constraints — robust without relying on
  local-model tool-calling.

### WS4 · Masked-metadata validation harness → **Milestone C** (critical, M3–5)
- `backend/eval/`: mask labels/types/units on known-good datasets, run the
  local pipeline, score recovered vs ground truth. Metrics: per-field accuracy,
  **hallucination rate**, confidence calibration → the ~90 % target.
  Provider-parametrized to produce an Anthropic-vs-Gemma-vs-APERTUS
  **scorecard** (also a dissemination artifact). Offline parts run in CI.

### WS5 · Integration + PoC → **Milestones D** (M6–7) & **E** (M8–9)
- D: end-to-end local runs on UNIL datasets; harden flaky-endpoint / context
  handling; curate a historical-control resource. E: run the existing VCG
  engine for one predefined use case; package synthetic-control CSV + stats
  report + FAIR exports into a PoC bundle.

### WS6 · Dissemination & packaging → **Milestone F** (M10–11)
- Docker-compose profile bundling local-LLM config; one-command setup; docs;
  example datasets + scorecard; workshop material. (GPL-3.0 already in place.)

## 5. Key risks & mitigations

| Risk | Mitigation |
|------|------------|
| Local tool-calling unreliability | Structured-output JSON-schema + KG-grounded enums + HITL review + validation harness (the grant's stated safeguard set). |
| Context window / PDF size on consumer hardware | Local text extraction + truncation/chunking. |
| Reproducibility across models | Fixed seeds where possible; scorecard tracking; masked-metadata regression tests. |

## 6. Notes for the proposal text (non-code)

- **Milestone numbering mismatch**: the Milestones table has A = knowledge graph
  @ M1, B = local LLM @ M2; the Gantt has A = local LLM @ M1, B = knowledge
  graph @ M3–4. Engineering-wise **B (provider layer) is foundational** and
  should lead or run parallel to A — reconcile the IDs before submission.
- The Methodology names **two different local models** (APERTUS vs
  Google/Gemma) and contains duplicated paragraphs — tighten before submission.
- Optional attachments to produce: FAIR→3R Sankey, raw-data→FAIR→VCG flowchart,
  interface screenshot/demo.

## 7. New / changed configuration (introduced by WS1)

| Env var | Purpose | Default |
|---------|---------|---------|
| `LLM_PROVIDER` | `anthropic` or `openai` (LM Studio) | `anthropic` |
| `LLM_BASE_URL` | OpenAI-compatible endpoint, e.g. `http://localhost:1234/v1` | — |
| `LLM_MODEL` | Local model id (fallback for all features) | — |
| `LLM_API_KEY` | Token for the local endpoint (LM Studio ignores it) | `lm-studio` |
| `LLM_MAX_DOC_CHARS` | Truncate extracted PDF text for local models | `60000` |
| `ENABLE_ONLINE_ENRICHMENT` | Enable CrossRef DOI lookup | `false` |

Per-feature model overrides (`PAPER_EXTRACTION_MODEL`, `FAIR_SCORER_MODEL`,
`COLUMN_ENRICHER_MODEL`, `ISSUE_FIXER_MODEL`, `VOCAB_DISCOVERY_MODEL`,
`VCG_ORCHESTRATOR_MODEL`, `HAIKU_MODEL`) continue to work for both providers;
when unset under `openai`, they fall back to `LLM_MODEL`.

## 8. Dissemination package (Milestone F)

`backend/scripts/build_dissemination.py` assembles a self-contained, offline-reproducible
evidence bundle for the grant. Run it from `backend/`:

```bash
python -m scripts.build_dissemination     # or: python scripts/build_dissemination.py
```

It lands in `dist/dissemination/` at the repo root and contains: the masked-metadata
provider scorecards (`scorecard_deterministic.md`, `scorecard_kg.md`, regenerated
in-process from the eval harness), the VCG proof-of-concept outputs under `vcg_poc/`,
the local-LLM deployment assets under `local_llm_deployment/`, and a `README.md` MANIFEST.
Headline metrics (eval accuracy / hallucination rate, VCG reliability score) are parsed
from the generated artifacts rather than hardcoded. The build is idempotent and is covered
by `backend/tests/test_dissemination.py`.

## 9. Frontend grant surfacing

Three grant-relevant features previously computed but not shown in the UI are now surfaced
(branch `fair-vcg-complete-3r-grant`):

- **Offline / local-LLM indicator** — the top-bar status chip reads the real provider/model
  from `/api/llm/status` (no longer hardcoded "Claude Haiku"); a configured `base_url` shows
  "Local LLM" with an "fully offline — no external API calls" tooltip, making the offline
  deployment story visible (`Layout.tsx`).
- **Knowledge-graph ontology grounding** — `ColumnProfilePage` now fetches `/api/uris/{id}`
  and shows the KG's per-column ontology matches (NCBITaxon / UBERON / UO …) as clickable IRI
  chips with confidence, wiring the previously-dead `getUriSuggestions` into the UI (Milestone A
  made visible).
- **3Rs Reduction impact** — `VCGResultsPage` adds a "Reduction (3Rs)" card quantifying live
  control animals reducible per future study, the synthetic expansion factor, and a
  reliability-gated substitution verdict — the headline animal-welfare metric for the 3RCC grant.
