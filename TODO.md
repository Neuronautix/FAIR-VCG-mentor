# Fix List — FAIR CSV Mentor

Generated from code review on 2026-05-02.

## V2 Plan — Local LLM, Multi-Paper Schema Builder, and Scientific HITL

Goal: make FAIR-VCG Mentor local-first and scientist-led. The LLM should help extract, compare, and explain schemas across several papers, but every scientific decision remains reviewable and approved by the expert user before it mutates the dataset, vocabulary, metadata, or VCG configuration.

### V2 branch
- [x] Create planning branch: `v2-local-llm-hitl-planning`
- [ ] Keep `main` clean until the v2 plan is reviewed and split into implementation PRs

### 1. Local LLM + external LLM API strategy

Recommended architecture: add a provider-neutral LLM gateway instead of coding directly against Claude/Anthropic in feature modules.

- [ ] Replace the Anthropic-specific `llm_service.py` surface with an `LLMProvider` interface:
	- `generate_structured(system, messages, schema, tools=None, options=None)`
	- `stream_structured(...)`
	- `healthcheck()`
	- provider metadata: model name, context window, local/cloud, supports tools, supports JSON schema, supports vision/PDF input
- [ ] Keep existing `call_haiku` behavior as an Anthropic adapter during migration so current paper extraction, FAIR scoring, vocabulary discovery, and VCG chat continue to work.
- [ ] Add an OpenAI-compatible adapter:
	- Supports OpenAI, Ollama, LM Studio, llama.cpp server, vLLM, and many hosted gateway APIs through `base_url`, `api_key`, and `model`.
	- Use this as the primary compatibility layer for local LLMs and for users who bring their own OpenAI-compatible endpoint.
- [ ] Add optional native adapters only where needed:
	- Anthropic adapter for Claude tool use and prompt caching.
	- Gemini adapter if multimodal PDF processing is materially better for a deployment.
	- Codex/OpenAI adapter through the same OpenAI-compatible path unless a feature needs an OpenAI-specific API.
- [ ] Add provider config to environment and UI:
	- `LLM_PROVIDER=none|ollama|openai_compatible|anthropic|gemini`
	- `LLM_BASE_URL=http://localhost:11434/v1`
	- `LLM_MODEL=qwen3:14b`
	- `LLM_API_KEY`, optional for local runtimes
	- per-task overrides: `LLM_MODEL_INGESTION`, `LLM_MODEL_SCHEMA_SYNTHESIS`, `LLM_MODEL_CHAT`
- [ ] Add capability-aware routing:
	- Use deterministic CSV profiling and templates first.
	- Use local LLM by default for text extraction, column role suggestions, schema synthesis, and HITL question generation.
	- Allow cloud LLM fallback only when enabled by the user and only for tasks marked as eligible.
	- Never send uploaded papers or unpublished lab data to cloud providers without explicit per-session consent.
- [ ] Enforce one structured-output contract across providers:
	- JSON Schema validation after every model call.
	- Ground all column names, values, units, and ontology terms against session data or approved vocabularies.
	- Queue all risky outputs as HITL suggestions; do not auto-apply.
	- Store provider, model, prompt version, schema version, confidence, and validation errors in the audit trail.
- [ ] Add local runtime documentation:
	- `ollama pull qwen3:14b`
	- configure `LLM_PROVIDER=ollama`
	- configure `LLM_BASE_URL=http://localhost:11434/v1`
	- expose hardware guidance and fallback models in the UI.

Recommended first local model:

- [ ] Start with **Qwen3-14B via Ollama** for v2 development.
	- Rationale: Apache-2.0 license, strong instruction/tool-following profile, 14.8B parameters, 32k native context and documented long-context extension, broad local runtime support.
	- Use a quantized build for ordinary lab workstations.
	- Treat it as the default "scientific assistant" for schema synthesis and HITL question drafting.
- [ ] Provide smaller fallback profiles:
	- `qwen3:8b` or similar 8B-class model for laptops with limited RAM/VRAM.
	- `llama3.1:8b` for deployments that prefer the Llama ecosystem and need a well-known 128k-context option.
	- Cloud Claude/Gemini/OpenAI only as opt-in escalation for difficult papers or long synthesis jobs.
- [ ] Add a model benchmark gate before declaring the local default stable:
	- 20-30 representative methods/result paragraphs from target domains.
	- Tasks: metadata extraction, column-role mapping, unit normalization, ontology suggestion, uncertainty detection, and question generation.
	- Metrics: schema validity, hallucinated column rate, ontology precision, useful-question rate, and expert correction burden.

### 2. Scientist-facing v2 feature backlog

The product story should not be "please do FAIR." It should be "upload your papers and data, get a scientifically defensible schema that can become VCG-ready and exportable."

- [ ] **Multi-paper study import**: upload 5-10 PDFs/DOIs/methods texts for one lab, project, or therapeutic area.
- [ ] **Evidence map**: show which paper supports each proposed metadata field, column role, unit, endpoint, covariate, and controlled value.
- [ ] **Schema consensus builder**: merge article-level schemas into one lab/project schema with conflict detection:
	- same concept, different names
	- same column name, different scientific meaning
	- same endpoint, different units
	- inconsistent control/treatment labels
	- missing covariates required for VCG validity
- [ ] **Scientist question queue**: ask the expert only when the system has material uncertainty or a scientific conflict, not for every extracted field.
- [ ] **FAIR-to-VCG readiness score**: translate FAIR improvements into concrete VCG consequences:
	- "This missing unit prevents endpoint harmonization."
	- "This missing control label prevents historical control pooling."
	- "This missing strain/sex/age field weakens covariate balance."
- [ ] **VCG-ready schema export**: export the approved schema as LinkML/YAML, CSVW, RO-Crate profile, and reusable FAIR-VCG template.
- [ ] **Methods-section generator**: generate auditable text describing schema construction, HITL review, VCG assumptions, and exclusions.
- [ ] **Reviewer/ethics committee pack**: produce a compact report with schema provenance, expert decisions, model uncertainty, VCG suitability, and FAIR deltas.
- [ ] **Ontology-assisted schema terms**: prefer canonical IRIs from OLS/BioPortal/UO/EFO/NCIT/CHEBI over free-text terms.
- [ ] **Lab schema memory**: reuse approved lab/project schemas for future datasets, with explicit versioning and diff review.
- [ ] **FAIR delta view**: show how each expert decision changes FAIR score, export quality, and VCG readiness.
- [ ] **Historical control pool readiness**: flag whether the schema captures enough fields to support future multi-study VCG generation.

### 3. Improved LLM ingestion with internal HITL and agent loop

Core design: article-level extraction agents produce evidence-backed candidate schemas; a synthesis agent compares them; a critic agent identifies uncertainty and conflicts; the expert resolves only meaningful scientific questions; the system then emits an approved project schema.

- [ ] Add a `StudyCorpus` model:
	- papers: DOI/PDF/text source, extracted text chunks, bibliographic metadata
	- article schemas: per-paper candidate schema with evidence spans
	- consensus schema: merged project-level schema
	- conflicts: unresolved differences across article schemas
	- expert decisions: question, answer, rationale, affected schema paths
- [ ] Add ingestion pipeline stages:
	1. Parse each paper into sections: title, abstract, methods, animals/materials, interventions, endpoints, statistics, supplementary tables.
	2. Extract per-paper metadata and schema candidates with evidence spans.
	3. Normalize units, endpoint names, groups, timepoints, and covariates.
	4. Align each paper schema to existing templates and ontologies.
	5. Synthesize a consensus schema across papers.
	6. Run critic checks for missing evidence, contradictions, weak confidence, ontology gaps, and VCG blockers.
	7. Generate a ranked HITL question queue for the scientist.
	8. Apply expert answers, re-run synthesis, and produce a versioned approved schema.
- [ ] Add internal agent roles:
	- `PaperExtractorAgent`: extracts structured claims from each paper with evidence spans.
	- `SchemaNormalizerAgent`: standardizes names, units, controlled values, and ontology candidates.
	- `SchemaSynthesisAgent`: merges article schemas into a consensus schema.
	- `ScientificCriticAgent`: finds contradictions, missing assumptions, and weak evidence.
	- `QuestionPlannerAgent`: converts uncertainty into minimal, high-value expert questions.
	- `ExpertDecisionAgent`: applies approved answers and records provenance.
- [ ] Add confidence semantics that drive HITL:
	- `auto_accept`: deterministic or high-confidence facts with direct evidence and no conflict.
	- `needs_review`: plausible but low-confidence extraction, weak ontology match, or high downstream impact.
	- `must_ask`: conflicting article evidence, VCG-critical missing field, ambiguous unit, or unclear scientific meaning.
	- `reject`: unsupported or hallucinated claims.
- [ ] Extend HITL categories:
	- `schema_field`
	- `schema_conflict`
	- `ontology_mapping`
	- `unit_normalization`
	- `vcg_assumption`
	- `corpus_schema_approval`
- [ ] Update HITL UI:
	- Group questions by scientific impact, not by model call.
	- Show evidence snippets and paper/source for each proposed field.
	- Let the expert approve, edit, reject, or answer a targeted question.
	- Keep a visible audit trail of expert decisions and model uncertainty.
- [ ] Add stopping rules for the agent loop:
	- Stop when no `must_ask` items remain and all VCG-critical fields are resolved.
	- Cap model iterations per corpus to avoid runaway loops.
	- Require explicit expert approval before marking a schema as project-approved.
- [ ] Add tests and evaluation:
	- Provider-contract tests with mocked local/cloud responses.
	- JSON-schema validation and grounding tests.
	- Multi-paper synthesis fixtures with known conflicts.
	- HITL transition tests for pending -> edited/rejected/applied/stale.
	- Regression benchmark for hallucinated columns, invalid units, and unnecessary questions.

### V2 implementation phases

- [ ] **Phase 0 - Baseline and risk control**
	- Freeze current v1 behavior with tests around existing LLM/HITL paths.
	- Document privacy rules for local vs cloud LLM use.
	- Add feature flags for all v2 ingestion routes.
- [ ] **Phase 1 - Provider abstraction**
	- Introduce `LLMProvider` and adapters.
	- Port current Anthropic calls behind the interface.
	- Add Ollama/OpenAI-compatible local path.
	- Add provider health endpoint and admin/debug UI.
- [ ] **Phase 2 - Corpus ingestion foundation**
	- Add `StudyCorpus` persistence.
	- Support multiple PDFs/DOIs/text blocks per corpus.
	- Store per-paper extraction results with evidence spans.
- [ ] **Phase 3 - Schema synthesis**
	- Implement per-paper schema extraction, normalization, conflict detection, and consensus schema generation.
	- Export consensus schema as a draft template.
- [ ] **Phase 4 - Scientist HITL loop**
	- Add new HITL categories and evidence-backed review UI.
	- Add question ranking and schema approval workflow.
	- Persist expert decisions and schema versions.
- [ ] **Phase 5 - VCG readiness integration**
	- Connect consensus schema to column profiling, templates, and VCG wizard defaults.
	- Show FAIR-to-VCG readiness consequences.
	- Generate reviewer/ethics committee pack.
- [ ] **Phase 6 - Validation**
	- Run local model benchmark.
	- Compare Qwen3-14B, Qwen3-8B, Llama 3.1 8B, and opt-in cloud models on the same corpus fixtures.
	- Pick the documented default based on correction burden, not leaderboard scores.

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
- [ ] **Ontology lookup integration (OLS / BioPortal / UO / EFO)** — replace free-text vocabulary suggestions with proposed IRIs from community ontologies. Issue HITL `schema_extension` suggestions carrying both the term and its ontology IRI so downstream FAIR exports can link to the canonical concept.
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
