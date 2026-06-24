# Fix List — FAIR CSV Mentor

Generated from code review on 2026-05-02. Grant workstream section added 2026-06-23.

## Grant: Local-LLM, Knowledge Graph & Validation (Swiss 3RCC) — updated 2026-06-23

Full plan in [`docs/grant-roadmap.md`](docs/grant-roadmap.md). Status of the
local-LLM / FAIR-VCG grant workstream:

### Done (merged)
- [x] EQIPD Quality System template — LLM-fillable, cross-standard crosswalks, paper-scoring (#14)
- [x] Provider-agnostic LLM layer — `LLM_PROVIDER` anthropic|openai (LM Studio), structured-output local path, local PDF→text, `provider_info()`, CrossRef gated behind `ENABLE_ONLINE_ENRICHMENT` (#15)
- [x] Masked-metadata validation harness — `backend/eval/`, deterministic baseline 100% raw / 54.5% blind, 0% hallucination (#16)
- [x] Preclinical knowledge graph + grounding — `backend/knowledge/` from the precliniverse schema; grounding + offline ontology IRIs (#17)

### In review (PRs open, CI green)
- [ ] Local-LLM deployment — docker `local-llm` profile + setup docs + smoke (#18)
- [ ] KG-grounded eval predictor — +50 pp blind-mode accuracy (0.25 → 0.75) (#19)
- [ ] Live grant roadmap + this TODO (#20)

### Remaining grant milestones
- [ ] **D — integration tests on academic data** (M6–7) — end-to-end headless run + artifact/metric capture. BLOCKED: anonymised UNIL dataset. (Can start on `test_data/synthetic_biological_descriptors.csv` as placeholder.)
- [ ] **E — proof-of-concept VCG report** (M8–9) — VCG engine on the curated historical-control dataset; bundle synthetic CSV + stats report + FAIR exports. BLOCKED: use-case spec.
- [ ] **F — dissemination package** (M10–11) — committed provider scorecard, docs, FELASA-2027 workshop material.
- [ ] **Live local-endpoint validation** — real provider scorecard (`python -m eval.run_eval --predictor kg-llm`) on LM Studio + Gemma/APERTUS. BLOCKED: live endpoint.

### Technical backlog (post-merge follow-ups)
- [ ] KG: expand concepts/value hooks from real data; add measurement concepts (organ weight, clinical chemistry) with UO/UCUM units.
- [ ] Wire KG grounding into the other LLM call sites (VCG orchestrator, issue fixer, FAIR scorer, template `llm-suggest`) — currently only the column enricher.
- [ ] Implement the optional online resolver layer (OLS4 / ORCID / ROR / MyGene) from the precliniverse `apis` registry, behind `ENABLE_ONLINE_ENRICHMENT`.
- [ ] Eval: unit-recovery scoring; expand ground-truth datasets; wire the deterministic eval into CI as a guardrail; commit a periodic provider scorecard.
- [ ] LLM: full PDF chunking for long papers (currently truncation via `LLM_MAX_DOC_CHARS`); validate APERTUS end-to-end.
- [ ] Frontend: show active provider/model in LLM status; surface KG `ontology_suggestions` in the column profile; KG-grounding indicator.
- [ ] Infra: resolve the local FastAPI/pydantic test-collection mismatch for `test_template_router` / `test_vcg_template_integration` (environment, not code; passes in clean CI).

## Roadmap — Column Understanding (Small + Fast)

Goal: improve automatic column/data understanding while keeping latency and complexity low.

### Stage 0 — Baseline and acceptance gates (no model)
- [x] Create a repeatable benchmark from `test_data/*.csv` using expected mappings for key roles:
	- identifier, treatment/group, outcome, covariate, date/time, metadata/provenance
- [x] Add a script/report that prints precision/recall and per-column confidence distribution
- [x] Define release gate for "good enough without LLM":
	- >= 0.85 precision on key roles
	- >= 0.80 recall on key roles
	- <= 5% columns flagged "ambiguous" in known templates

### Stage 1 — Heuristic uplift (deterministic)
- [x] Expand synonym dictionaries for life-science terms:
	- ALT/AST variants, dose/unit aliases, control/group labels, sex/strain/age forms
- [x] Add value-shape validators:
	- ID regexes, date parsing, numeric+unit coupling, categorical cardinality checks
- [x] Emit `inferred_role` + `confidence` + `reason_codes` per column
- [x] Add unit tests covering all current CSV examples in `test_data/`

### Stage 2 — User-in-the-loop disambiguation (still no LLM)
- [x] Add low-confidence prompts in wizard/chat:
	- ask only for columns below threshold (e.g., confidence < 0.65)
- [x] Save confirmed mappings as reusable templates by dataset profile/signature
- [x] Re-apply templates automatically on upload before running advanced logic
- [x] Track correction rate and time-to-confirm metrics

### Stage 3 — Lightweight semantic layer (optional, non-LLM)
- [ ] Add optional embedding match against curated label bank/ontology aliases
- [ ] Use this only for unresolved columns after Stage 1+2
- [ ] Keep strict latency budget (e.g., < 200 ms per 100 columns on warm cache)
- [ ] Add fallback to deterministic heuristics if semantic layer unavailable

### Stage 4 — LLM assist (gated rollout)
- [ ] Add LLM path behind feature flag and only for hard/ambiguous cases
- [ ] Restrict LLM output to structured JSON schema (role, confidence, rationale)
- [ ] Log disagreement between heuristic and LLM predictions for audit
- [ ] Add timeout + safe fallback to non-LLM path

### When LLM becomes critical
- [ ] Treat LLM as critical only when all are true for >= 2 iterations:
	- Stage 1-3 plateau below target (cannot reach >= 0.90 precision and >= 0.85 recall)
	- Ambiguity remains > 10% on newly ingested partner datasets
	- Manual correction burden stays high (> 2-3 clarifications per dataset)
	- New schema diversity outpaces rule/template maintenance capacity

### Recommended implementation order
- [x] First implement Stage 0 and Stage 1 (highest ROI, lowest risk)
- [x] Then Stage 2 template memory (largest UX gain)
- [ ] Add Stage 3 only if ambiguity remains materially high
- [ ] Add Stage 4 (LLM) last, as selective escalation rather than default path

## Vocabulary, HITL, and schema verification (follow-ups)

- [ ] **Schema verification pass** — when the user clicks "Validate vocabulary", run a structural pre-flight that flags weird/inconsistent terms (e.g., unit fragments that don't parse, duplicate semantic-type assignments across columns). Surface findings inline before flipping `validated=True`.
- [ ] **Per-field templates** — let the user save vocabulary subsets as named templates (e.g., `pharmacology_units`, `arrive_metadata_keys`, `oncology_study_types`) and re-apply them to fresh sessions. Hooks into the existing `template_store.py`.
- [~] **Ontology lookup integration (OLS / BioPortal / UO / EFO)** — _partially done:_ the preclinical KG (PR #17) now grounds columns to ontology schemes and proposes offline IRIs (e.g. species → NCBITaxon) via `uri_suggester.ontology_suggestions`. Still open: live OLS/BioPortal resolution + issuing these as HITL `schema_extension` suggestions carrying the ontology IRI.
- [ ] **Vocabulary diff view** — show `history` entries on the Vocabulary panel so the user can see what each version added/removed and why.
- [ ] **Discover from dataset description** — wire a "scan dataset description / methods" mode in `llm_vocab_discovery.py` (plain text input, not PDF only).
- [ ] **Auto-stale on column edit** — bump vocabulary version when `PUT /api/columns` adds new sample values that change `controlled_values`.
- [ ] **Schema_version aware re-suggestion** — UI "regenerate" action on stale HITL cards that re-asks Haiku against the latest vocabulary instead of forcing the user to retrigger from each origin page.

## Paper Import & LLM Features

- [ ] **paper_extractor.py** — switch to Anthropic `tool_use` for guaranteed structured output (no JSON parse fallback needed)
- [ ] **llm_fair_scorer.py** — new module: Claude qualitative commentary on all four FAIR dimensions
- [ ] **GET /api/fair-score/{id}/llm** — new endpoint calling `llm_fair_scorer`; returns per-dimension verdict + commentary
- [ ] **FAIRScorePage.tsx** — "AI Assessment" card with LLM verdicts, per-dimension commentary, and top priority recommendation
- [ ] **UploadPage.tsx** — after CSV upload, if `paperExtraction` is in store, auto-call `saveMetadata` and show "Pre-filled from paper" toast
- [ ] **MetadataWizardPage.tsx** — pre-fill empty form fields from `paperExtraction.dataset_metadata`; show "from paper" Chip on pre-filled fields
- [ ] **VCGWizardPage.tsx Step 2** — highlight outcome/covariate chips matching `vcg_hints`; pre-fill control group label if empty
- [ ] **ColumnProfilePage.tsx** — show paper-hint badges on columns matching `vcg_hints.outcome_columns` / `covariate_columns`
- [ ] Persist `session["paper_extraction"]` in SQLite and add GET `/api/paper/{id}` retrieval endpoint
- [ ] Streaming paper extraction via SSE + `client.messages.stream()`
- [ ] CrossRef DOI input on Paper Import page

## Backend

### Critical bugs
- [x] `vcg/agents/vcg_bootstrap.py:80` — Zero-variance columns produce NaN in Spearman matrix → degenerate copula; fall back to identity for those columns
- [x] `vcg/agents/standardization_agent.py:94` — `mode().iloc[0]` throws IndexError on all-NaN categorical column; guard with `len(m) > 0`
- [x] `main.py:95` — `_load_session` silently returns None on exception; add logging before returning
- [x] `vcg/vcg_engine.py:52` — Misleading error when control group is empty due to type mismatch (int vs string); coerce `control_value` type before filtering

### Error handling
- [x] `vcg/agents/stats_agent.py:71` — Replace `if p == p` NaN check with `not np.isnan(p)`
- [x] `uri_suggester.py` — Validate `base_uri` before using it in URI construction
- [x] `export_engine.py:30` — Deduplicate normalised column names to prevent silent collisions
- [x] `standardization_agent.py:84` — Document the 50% threshold for numeric vs categorical imputation decision

### Design / duplication
- [x] `csv_profiler.py` + `vcg/vcg_wizard.py` — Extract shared `IDENTIFIER_PATTERNS` and control-value keywords to `vcg/constants.py`
- [x] `vcg/orchestrator.py` — Add `_parse_yes_no()` helper to consolidate free-text parsing across all 8 state handlers
- [x] `context_model.py` — Replace manual `dict_to_*` conversion functions with `dataclasses.asdict()` / `dataclasses.replace()`
- [x] `fair_engine.py` — Extract inline `has()` helper to module level so individual criteria can be unit-tested

### Performance
- [x] `main.py` (`_prepare_exports`) — `compute_fair_score()` and `suggest_uris()` recomputed on every export call; memoize against session state

## Frontend

### Bugs
- [x] `VCGWizardPage.tsx:273` — When `bioColumns.length === 0`, all columns shown instead of empty state (inverted condition)
- [x] `VCGResultsPage.tsx:81` — Polling calls API without guarding `datasetId === null`; add early return
- [x] `VCGPage.tsx:50` — `addChatMessage`/`setVCGStatus` missing from `useEffect` dependency array; causes stale closures
- [x] `FAIRScorePage.tsx:44` — `load` missing from effect dependency array
- [x] `MetadataWizardPage.tsx:99` — Remove `setFairScore(null as never)` cast; use proper `FAIRScore | null` union

### Missing states / UX
- [x] `ExportPage.tsx:110` — Replace `alert()` on export failure with MUI `Snackbar`/`Alert`
- [x] `OverviewPage.tsx` — Add null guard before `.map()` on `tableStructure.detected_*` arrays
- [x] `MetadataWizardPage.tsx:80` — Surface error to user when `getMetadata()` fails
- [x] `CovariateBalanceTable.tsx:45` — Render `"—"` instead of `"Infinity"` / `"NaN"` for non-finite SMD values

### Type safety
- [x] `Layout.tsx:92` — Replace `(item as any).vcgItem` with a typed optional field on the nav item interface
- [x] `useStore.ts` — Clear `base_uri` default on `reset()` so it doesn't persist across uploads

### Accessibility
- [x] `ChatInterface.tsx:150` — Add `aria-label="Message input"` to the message TextField
- [x] `ColumnProfilePage.tsx:309` — Improve Snackbar accessibility (longer duration or persistent until dismissed)
