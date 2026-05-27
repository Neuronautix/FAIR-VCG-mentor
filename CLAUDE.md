# FAIR-VCG Mentor — CLAUDE.md

## Project Overview

FAIR-VCG Mentor is a web application with two main capabilities:

1. **FAIR Assessment** — profiles CSV datasets against the [FAIR data principles](https://www.go-fair.org/fair-principles/) (Findable, Accessible, Interoperable, Reusable), scores them on a 105-point rubric, guides metadata enrichment through a wizard, and exports results in standards-compliant formats (Frictionless DataPackage, CSVW, JSON-LD, RO-Crate).

2. **Virtual Control Group (VCG) Generation** — generates statistically rigorous synthetic control cohorts from a real concurrent control group, using either a Gaussian copula bootstrap or KDE/Normal sampling, with optional covariate balancing. Configured through a rule-based chat assistant or a four-step wizard; no external LLM API required.

---

## Repository Structure

```
FAIR-vcg-mentor/
├── CLAUDE.md                 # This file
├── docker-compose.yml        # Orchestrates backend + frontend
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py               # FastAPI app, FAIR endpoints + VCG router registration
│   ├── csv_profiler.py       # Encoding/delimiter detection, column type & semantic inference
│   ├── fair_engine.py        # FAIR scoring (100-pt rubric) & issue detection
│   ├── entity_detector.py    # Table-shape inference (repeated measures, long/wide)
│   ├── uri_suggester.py      # Linked-data URI pattern generation
│   ├── export_engine.py      # Multi-format export (CSV, CSVW, JSON-LD, RO-Crate, etc.)
│   ├── template_engine.py    # Template loader, matcher, validator, conformance reporting
│   ├── template_router.py    # FastAPI router — /api/templates/* and /api/{id}/template/* endpoints
│   ├── linkml_import.py      # LinkML schema → starter template converter
│   ├── prepare_engine.py     # PREPARE study plan + checklist export (planning counterpart to ARRIVE)
│   ├── templates/
│   │   ├── arrive-v2.yaml    # ARRIVE 2.0 reporting standard (dataset-level metadata)
│   │   ├── mnms-v1.yaml      # MNMS schema for DVC cages (conforms_to ARRIVE)
│   │   ├── namo-nam-assay-v1.yaml  # NAMO NAM dose-response / functional assay (hand-crafted)
│   │   ├── prepare-v1.yaml                  # PREPARE 15-topic planning checklist (Smith et al. 2018)
│   │   ├── arrive-prepare-crosswalk-v1.yaml # ARRIVE 2.0 + PREPARE combined (conforms_to both)
│   │   └── user/             # User-uploaded custom templates
│   └── vcg/
│       ├── __init__.py
│       ├── vcg_router.py     # FastAPI router — all /api/vcg/* endpoints
│       ├── orchestrator.py   # Rule-based FSM chat engine (9 states, no LLM)
│       ├── vcg_engine.py     # Four-agent pipeline orchestrator (sync, run via to_thread)
│       ├── vcg_wizard.py     # Wizard payload validation
│       ├── context_model.py  # Dataclasses: ResearchContext, ColumnRoles, VCGConfig
│       ├── vcg_report.py     # Markdown statistical report generator
│       ├── constants.py      # CONTROL_KEYWORDS list for auto-detecting control group
│       ├── agents/
│       │   ├── ingestion_agent.py       # Data validation, control-row extraction, n_control
│       │   ├── standardization_agent.py # Unit harmonisation, missing-value imputation
│       │   ├── vcg_bootstrap.py         # Gaussian copula bootstrap (recommended for N ≥ 15)
│       │   ├── vcg_synthetic.py         # KDE/Normal sampling (fallback for N < 15)
│       │   └── stats_agent.py           # Effect sizes, CIs, reliability score, diagnostics
│       └── utils/
│           ├── covariate_balance.py     # Balance report: SMD, distributional overlap
│           └── distributions.py        # Distribution fitting (Normal/LogNormal/Gamma)
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── App.tsx
        ├── api/client.ts         # Axios API client (maps to all backend endpoints)
        ├── store/useStore.ts     # Zustand global state
        ├── components/
        │   ├── Layout.tsx
        │   ├── FAIRScoreBreakdown.tsx
        │   ├── IssueCard.tsx
        │   ├── AgentStatusBar.tsx
        │   └── ChatInterface.tsx
        └── pages/
            ├── UploadPage.tsx
            ├── OverviewPage.tsx
            ├── ColumnProfilePage.tsx
            ├── FAIRScorePage.tsx
            ├── MetadataWizardPage.tsx
            ├── ExportPage.tsx
            ├── VCGPage.tsx           # Chat interface + generation status polling
            ├── VCGWizardPage.tsx     # Four-step configuration wizard
            ├── VCGResultsPage.tsx    # Results, diagnostics, export
            └── TemplateSelectorPage.tsx  # Template selection, conformance report, custom upload
```

---

## Running the Project

```bash
# Start both services with live reload (recommended)
docker-compose up

# Backend only (port 8000)
cd backend && pip install -r requirements.txt && uvicorn main:app --reload

# Frontend only (port 5173)
cd frontend && npm install && npm run dev
```

Backend API: `http://localhost:8000`
Frontend: `http://localhost:5173`
OpenAPI docs: `http://localhost:8000/docs`

**Docker note:** The Vite proxy target is set via `VITE_BACKEND_URL`. In `docker-compose.yml` this is `http://backend:8000` (Docker service name). For native development the default `http://localhost:8000` is used.

---

## Architecture & Data Flow

### FAIR pipeline

```
User uploads CSV / Excel
        │
        ▼
POST /api/upload
  ├── csv_profiler.py    → encoding, delimiter, column types, semantic types, units
  ├── entity_detector.py → table shape, primary entity, repeated-measures detection
  └── fair_engine.py     → data quality & metadata issues list
        │
        ▼
Session stored in SQLite (UUID key) + in-memory dict
        │
        ▼
User edits column metadata / fills dataset metadata wizard
        │
PUT /api/columns/{id}   → rerun issue detection
PUT /api/metadata/{id}  → update dataset-level metadata
        │
        ▼
GET /api/fair-score/{id}
  └── fair_engine.py     → score F/A/I/R dimensions (25/20/30/30 pts)
        │
        ▼
GET /api/export/{id}/{type}
  └── export_engine.py   → cleaned-csv | data-dictionary | frictionless |
                           csvw | jsonld | report | rocrate
```

### VCG pipeline

```
User configures via chat (VCGPage) or wizard (VCGWizardPage)
        │
PUT /api/vcg/{id}/wizard  → save ColumnRoles + VCGConfig + ResearchContext
        │
POST /api/vcg/{id}/generate
  └── vcg_engine.run_vcg_pipeline() [asyncio.to_thread]
        ├── DataIngestionAgent     → validate data, extract control rows, compute n_control
        ├── DataStandardizationAgent → harmonise units, impute missing values
        ├── BootstrapVCGAgent      → Gaussian copula (N ≥ 15)
        │   OR SyntheticVCGAgent   → KDE/Normal (N < 15)
        └── StatsAgent             → effect sizes, CIs, reliability score, diagnostics
        │
        ▼
session["vcg"]["vcg_status"] = "done" | "failed"
        │
Frontend polls GET /api/vcg/{id}/status every 2 s
        │
        ▼ (on "done")
GET /api/vcg/{id}/results    → balance report, stats, reliability score
GET /api/vcg/{id}/export/vcg-csv     → synthetic CSV download
GET /api/vcg/{id}/export/vcg-report  → Markdown statistical report
```

**Session model:** State lives in a Python dict keyed by UUID, persisted to SQLite via `_save_session` / `_load_session` in `main.py`. The `df` (pandas DataFrame) and `original_bytes` are excluded from JSON serialisation and reconstructed on load.

### Template layer

```
On /api/upload:
  └── template_engine.suggest_templates(columns, metadata)
        ├── if top score ≥ 0.9 → auto-assign, run validation, append conformance issues
        └── else → store candidates for user review

User opens /templates page (TemplateSelectorPage)
  ├── GET /api/templates                  → registry (builtin + user)
  ├── GET /api/{id}/template/suggestions  → ranked candidates with reasons
  ├── POST /api/{id}/template/{tid}       → assign + validate + append issues
  ├── DELETE /api/{id}/template           → unassign + strip template issues
  ├── GET /api/{id}/template/validation   → re-run validation (read-only)
  ├── POST /api/templates                 → upload custom template (YAML/JSON)
  └── POST /api/templates/import-linkml   → convert LinkML schema → starter template

Downstream effects (when template assigned):
  ├── GET /api/vcg/{id}/wizard-prefill    → overlays vcg_defaults (treatment_col,
  │                                         outcome_cols, covariates, clustering)
  │                                         and returns template_locked + clustering_warning
  ├── POST /api/vcg/{id}/generate         → also runs template.predefined_analyses
  │                                         (arrive_completeness, cage_effect_check)
  │                                         attached to vcg_results.template_analyses
  └── GET /api/fair-score/{id}            → adds declares_template_conformance criterion
                                            under R dimension (5 pts)
```

**Templates conform to a hierarchical model.** `mnms-v1` declares `conforms_to: [arrive-v2]` and inherits ARRIVE's `required_metadata`. MNMS columns annotated with `arrive_section` satisfy specific ARRIVE fields automatically, so the conformance report cross-walks column presence against the reporting standard.

**ARRIVE + PREPARE crosswalk.** `arrive-prepare-crosswalk-v1` declares `conforms_to: [arrive-v2, prepare-v1]` and inherits the full required-metadata sets of both parents. `RequiredMetadata` entries support two additional keys: `prepare_section` (Optional[str], the PREPARE topic label) and `crosswalk` (List[str], sibling field_ids that satisfy this entry when filled). Conformance entries produced by `validate_against_template` carry both `arrive_section` and `prepare_section` keys (either may be None) alongside the legacy `section` field. When any field_id listed in an entry's `crosswalk` is already satisfied, the engine flips that entry to `status: satisfied` and records `satisfied_by: {"metadata": <other_field_id>, "via_crosswalk": True}`. Crosswalks are directional — only entries that *declare* a crosswalk list are auto-satisfied; the reverse direction is not inferred.

**Two compliance tiers per template:**
- **Column-level** (`required_columns`): the CSV must contain matching columns.
- **Dataset-level** (`required_metadata`): the metadata wizard must contain matching fields.

**Missing fields degrade, never block.** Failed conformance items appear in `session["issues"]` with `category="template_compliance"` and reduce the FAIR R-dimension score (`declares_template_conformance` criterion: 0/1/3/5 pts based on % satisfaction). VCG generation still runs.

**Auto-assign threshold: score ≥ 0.9.** Score = 0.7 × (matched_required_columns / total) + 0.3 × (matched_required_metadata / total). Below 0.9, candidates are surfaced as suggestions on the upload banner and the Templates page.

---

## Backend Module Reference

### `main.py`
- All FAIR FastAPI route handlers
- SQLite session persistence (`_save_session`, `_load_session`, `_init_db`)
- CORS origins configurable via `CORS_ORIGINS` env var
- Registers `vcg_router` via `init_vcg_router(sessions, _save_session, _load_session)` then `app.include_router(vcg_router)`
- Key routes:
  - `POST /api/upload` → profile + detect issues, return `dataset_id`
  - `GET /api/profile/{id}` → import info, columns, table structure
  - `GET /api/issues/{id}` → detected quality/metadata issues
  - `PUT /api/columns/{id}` → update column metadata, rerun issue detection
  - `GET|PUT /api/metadata/{id}` → dataset-level metadata
  - `GET /api/fair-score/{id}` → compute + return FAIR score
  - `GET /api/uris/{id}` → generate URI suggestions
  - `GET /api/export/{id}/{type}` → stream export file
  - `GET /api/export/{id}/prepare` → PREPARE planning zip (study plan + checklist)

### `csv_profiler.py`
- `profile_csv(file_bytes, filename)` → `ProfileResult`
- Detects: encoding (chardet), delimiter (csv.Sniffer), data types, semantic types, units
- Semantic types: `identifier | measurement | biological_descriptor | experimental_condition | time_variable | free_text_note | metadata_field | categorical | unknown`
- Returns column profiles with confidence scores, sample values, missing-value counts
- Returns key `df` (typed DataFrame) and `content` (decoded string); both are popped by `main.py` before storing

### `fair_engine.py`
- `compute_fair_score(import_info, columns, table_structure, metadata, issues)` → `FAIRScore`
- `detect_issues(import_info, columns, table_structure)` → `list[Issue]`
- FAIR rubric: F=25, A=20, I=30, R=30 points (5 pts per criterion); R includes `declares_template_conformance` (template layer, scaled 0/1/3/5)
- Issue severities: `high | medium | low`

### `entity_detector.py`
- `detect_entity_structure(df, columns)` → `TableStructure`
- Infers: primary entity, secondary entity, table shape, row representation, detected identifier/measurement/categorical/time columns
- Shape options: `one_row_per_entity | repeated_measures | repeated_measures_long_format | wide_measurement_format | tabular_data`

### `uri_suggester.py`
- `suggest_uris(columns, metadata, import_info)` → `URISuggestions`
- Generates: dataset URI, observation pattern, entity URIs, column URIs

### `export_engine.py`
- Exports: `cleaned-csv | data-dictionary | frictionless | csvw | jsonld | report | rocrate`
- All functions return `bytes`; `main.py` streams them directly without writing to disk

### `prepare_engine.py`
- PREPARE planning export. `generate_prepare_zip()` returns a zip of `prepare_study_plan.md` (pre-filled study plan by 15 PREPARE topics) and `prepare_checklist.md` (status table for all PREPARE sub-items). Reads from `session["metadata"]` and `session["template_validation"]`; resolves via ARRIVE↔PREPARE crosswalks when the assigned template links them.

---

## VCG Module Reference

### `vcg/vcg_router.py`
FastAPI `APIRouter` mounted at `/api/vcg`. Receives injected references to `sessions`, `_save_session`, and `_load_session` from `main.py` via `init_vcg_router()`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/{id}/wizard-prefill` | GET | Auto-fill wizard from profiled column data |
| `/{id}/wizard` | PUT | Save `column_roles`, `vcg_config`, `research_context` |
| `/{id}/chat/start` | POST | Start conversation, return first agent message |
| `/{id}/chat/respond` | POST | Send user message, return next agent message |
| `/{id}/conversation` | GET | Full conversation history |
| `/{id}/generate` | POST | Start async pipeline; returns immediately with `vcg_status: running` |
| `/{id}/status` | GET | Poll status: `not_started | running | done | failed` |
| `/{id}/results` | GET | Results dict (excluding VCG CSV bytes) |
| `/{id}/export/vcg-csv` | GET | Stream synthetic CSV |
| `/{id}/export/vcg-report` | GET | Stream Markdown statistical report |

### `vcg/orchestrator.py`
Rule-based finite-state machine. No external LLM required.

States (in order): `GREETING → TREATMENT_CONFIRM → ENDPOINT_SELECT → COVARIATE_SELECT → SAMPLE_SIZE → METHOD_SELECT → SUMMARY_CONFIRM → READY_TO_BUILD`

Each state produces a structured agent message with `content` (Markdown), `state`, `options` (quick-reply button labels), and `ready_to_build` (bool). When `ready_to_build` is `true`, the frontend triggers `POST /generate`.

### `vcg/vcg_engine.py`
`run_vcg_pipeline(dataset_id, session, sessions_dict, save_fn)` runs synchronously inside `asyncio.to_thread`. Updates `session["vcg"]` in-place. Sets `vcg_status` to `"done"` or `"failed"`.

Agent sequence:
1. `DataIngestionAgent` — validates types, extracts control rows (`df[treatment_col] == control_value`), reports `n_control`
2. `DataStandardizationAgent` — handles missing values in outcome and covariate columns
3. `BootstrapVCGAgent` (N ≥ 15) or `SyntheticVCGAgent` (N < 15) — generates synthetic DataFrame
4. `StatsAgent` — computes per-endpoint effect sizes (Cohen's d), confidence intervals, Kolmogorov-Smirnov test, overall reliability score

### `vcg/context_model.py`
Three dataclasses serialised to/from dicts stored in `session["vcg"]`:
- `ResearchContext` — `domain`, `study_type`, `design`, `confirmed_by_user`
- `ColumnRoles` — `treatment_col`, `control_value`, `treatment_value`, `outcome_cols`, `covariate_cols`, `subject_id`, `time_col`, `exclude_cols`
- `VCGConfig` — `method` (`auto|bootstrap|synthetic`), `n_synthetic`, `seed`, `bootstrap_iters`, `confidence_level`

`DEFAULT_VCG_SESSION()` produces the initial `session["vcg"]` dict with all fields zeroed/empty.

### `vcg/agents/vcg_bootstrap.py`
Gaussian copula bootstrap. Fits marginal distributions (Normal / LogNormal / Gamma) to each outcome column, models inter-column correlations via a Gaussian copula, and samples `n_synthetic` rows. Preserves covariate distributions if `covariate_cols` is non-empty. Recommended for N ≥ 15.

### `vcg/agents/vcg_synthetic.py`
KDE or Normal sampling. Independently samples each column from its fitted kernel density estimate. More conservative; recommended for N < 15. Does not preserve inter-column correlations.

### `vcg/agents/stats_agent.py`
Produces per-endpoint statistics: mean ± SD for real vs VCG, Cohen's d, 95% CI, KS test p-value. Computes an overall `reliability_score` (0–1) based on effect size and distributional similarity. Flags warnings when n_control is very small or when KS divergence is high.

---

## Frontend Reference

### State (`store/useStore.ts`)
Central Zustand store. Key slices:
- **FAIR:** `datasetId`, `importInfo`, `columns`, `tableStructure`, `issues`, `fairScore`, `metadata`, `uriSuggestions`
- **VCG:** `vcgConversation`, `vcgStatus`, `vcgResults`
- Actions: `setUploadResult`, `setColumns`, `updateColumn`, `setMetadata`, `setFairScore`, `addChatMessage`, `setVCGStatus`, `setVCGResults`, `reset`

### API Client (`api/client.ts`)
Thin Axios wrapper. Base URL is `/api` (proxied to backend by Vite). Each backend endpoint has a corresponding exported function. VCG functions: `getVCGWizardPrefill`, `saveVCGWizard`, `startVCGChat`, `respondVCGChat`, `startVCGGeneration`, `getVCGStatus`, `getVCGResults`, `getVCGConversation`, `vcgExportUrl`.

### Pages

| Page | File | Responsibility |
|------|------|----------------|
| Upload | `UploadPage.tsx` | File drag-drop, POST /upload, redirect to /overview |
| Overview | `OverviewPage.tsx` | Summary stats, table shape card, issues list |
| Column Profile | `ColumnProfilePage.tsx` | Editable table: label, description, type, units, vocab, URI |
| FAIR Score | `FAIRScorePage.tsx` | Score gauge + dimension breakdown + recommendations |
| Metadata Wizard | `MetadataWizardPage.tsx` | Dataset-level metadata form |
| Export | `ExportPage.tsx` | Per-format download buttons + RO-Crate bundle |
| VCG Chat | `VCGPage.tsx` | Rule-based chat + generation trigger + status polling |
| VCG Wizard | `VCGWizardPage.tsx` | Four-step form: context / column roles / stats config / review |
| VCG Results | `VCGResultsPage.tsx` | Reliability score, balance diagnostics, VCG CSV + report download |

**VCG status polling** (`VCGPage.tsx`): `setInterval` at 2 s calls `GET /api/vcg/{id}/status`. Checks `statusData.vcg_status` (not `statusData.status`) for `"done"` or `"failed"`. On `"done"`, clears the interval, fetches results, and navigates to `/vcg/results`.

---

## Functionality & Usability Assessment

### What Works Well

**Full end-to-end FAIR pipeline.** Upload → profile → score → enrich → export runs without external dependencies. Semantic type inference covers most life-sciences CSV naming conventions.

**VCG pipeline is self-contained.** The rule-based orchestrator requires no LLM API key. The four-agent pipeline runs locally using scipy/statsmodels. Gaussian copula bootstrap preserves inter-endpoint correlations, which naive per-column sampling does not.

**Two VCG entry points.** Chat suits first-time users; the wizard suits users who already know their configuration. Both converge on the same `session["vcg"]` state.

**Seven FAIR export formats.** Frictionless DataPackage, W3C CSVW, Schema.org JSON-LD, and RO-Crate are covered. Few open-source tools provide all of these together.

**SQLite persistence.** Sessions survive server restarts. The DataFrame is reconstructed from stored bytes on load rather than serialised.

### Known Gaps

| Gap | Severity | Notes |
|-----|----------|-------|
| No tests | High | Zero test coverage across backend and frontend. Any refactor of `vcg_engine.py`, `vcg_bootstrap.py`, or `stats_agent.py` carries high regression risk. |
| Hardcoded semantic patterns | Medium | Column-type inference relies on name patterns. Unusual naming conventions score poorly with no fallback. |
| VCG requires one-shot control group | Medium | The pipeline extracts control rows by matching `treatment_col == control_value` as strings. Type mismatches (int vs string) cause an empty control set and pipeline failure. |
| No ontology lookup | Medium | Controlled vocabulary fields accept free text; no integration with OLS, BioPortal, or SKOS. |
| VCG chat state not restored on reload | Low | `vcgConversation` lives in Zustand (not persisted to SQLite). Reloading the page loses the conversation but not the VCG config. |
| No diff/versioning | Low | No way to compare FAIR score before and after metadata edits. |
| Single-user only | Low | No auth, no session namespacing by user. |

---

## Multi-Agent Development Guidelines

### Ownership Boundaries

| Domain | Files | Agent Role |
|--------|-------|------------|
| **Backend – Analysis** | `csv_profiler.py`, `entity_detector.py` | Improve semantic detection, add column patterns, fix encoding edge cases |
| **Backend – Scoring** | `fair_engine.py` | Refine FAIR rubric, add/remove criteria, tune issue thresholds |
| **Backend – Export** | `export_engine.py`, `uri_suggester.py` | Add/fix export formats, validate against standards |
| **Backend – API** | `main.py` | Add endpoints, fix session logic, manage persistence layer |
| **Backend – VCG Core** | `vcg/vcg_engine.py`, `vcg/context_model.py`, `vcg/constants.py` | Pipeline orchestration, data model changes |
| **Backend – VCG Agents** | `vcg/agents/*.py`, `vcg/utils/*.py` | Statistical methods, agent logic, distribution fitting |
| **Backend – VCG Chat** | `vcg/orchestrator.py`, `vcg/vcg_wizard.py` | Conversation states, wizard validation |
| **Backend – VCG Router** | `vcg/vcg_router.py` | API endpoints for VCG sub-system |
| **Backend – Templates** | `template_engine.py`, `template_router.py`, `templates/*.yaml` | Template schema, loader, matcher, validator, conformance reporting |
| **Frontend – Pages** | `pages/*.tsx` | UI layout, user flows, form behaviour |
| **Frontend – State** | `store/useStore.ts`, `api/client.ts` | State shape changes, API contract alignment |
| **Frontend – Components** | `components/*.tsx` | Shared UI components |
| **Testing** | `backend/tests/`, `frontend/src/__tests__/` | Write and run tests; no logic changes |
| **Docs & Config** | `CLAUDE.md`, `docker-compose.yml`, `requirements.txt`, `package.json` | Documentation, dependency updates |

### Coordination Rules

1. **One agent per boundary per session.** Do not have two agents editing `vcg_engine.py` simultaneously.

2. **API contract is a shared interface.** Any agent changing a backend endpoint signature (`main.py` or `vcg_router.py`) or the Zustand store shape (`useStore.ts`) must also update the counterpart. State the contract change explicitly in the commit message.

3. **Session data shape is a coordination point.** `session["vcg"]` is read by `vcg_router.py`, `vcg_engine.py`, and the frontend results page. If you rename a key or add a required field, grep for all usages and update them in the same commit.

4. **VCG status field is `vcg_status`, not `status`.** The router returns `{"vcg_status": ..., "vcg_error": ...}`. The frontend polls `statusData.vcg_status`. Do not rename this field.

5. **Do not change export format schemas silently.** Changes to Frictionless, CSVW, JSON-LD, or RO-Crate output may break downstream consumers. Document schema changes in commit messages.

6. **Prefer additive changes.** Add new orchestrator states, agent steps, or scoring criteria rather than replacing existing ones until there is test coverage for the replaced behaviour.

7. **Tests live alongside source.** Backend tests in `backend/tests/`, frontend tests co-located as `*.test.tsx`. Testing agents must not modify source files.

### Suggested Parallel Tasks

Safe to run in parallel:

| Task | Safe to run in parallel with |
|------|------------------------------|
| Add unit tests for `csv_profiler.py` | Any frontend task; VCG agent changes |
| Add unit tests for `vcg_bootstrap.py` | Any frontend task; FAIR scoring changes |
| Add unit tests for `stats_agent.py` | Any frontend task; FAIR export changes |
| Improve VCGResultsPage visualisations | Any backend-only task |
| Add ontology term search endpoint | Frontend column profile UI changes |
| Add README screenshots | Any task |

Must be serialised:

| Task | Must wait for |
|------|--------------|
| Add auth/multi-tenancy | Session shape finalised |
| Persist VCG conversation to SQLite | Session model change reviewed |
| Add SHACL validation for JSON-LD | JSON-LD export format stabilised |
| Frontend ontology term picker | Backend ontology search endpoint |
| LLM-powered orchestrator | Rule-based orchestrator tests written |

### Commit Message Convention

```
<scope>: <imperative summary>

<optional body explaining why, not what>
```

Scope values: `backend`, `frontend`, `api`, `export`, `scoring`, `profiler`, `vcg`, `vcg-agents`, `vcg-chat`, `tests`, `docs`, `deps`, `config`

Examples:
```
vcg-agents: use Gamma distribution fallback when LogNormal fit diverges
vcg-chat: add REPEAT_MEASURES state for longitudinal study detection
scoring: add 5-pt criterion for machine-readable license URI
frontend: show per-endpoint KS p-value in VCGResultsPage
tests: add bootstrap agent tests for N=8 small-sample path
```

### Environment Setup for Agents

```bash
# Backend — install deps and run with auto-reload
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend — install deps and run dev server
cd frontend
npm install
npm run dev          # http://localhost:5173
npm run type-check   # TypeScript check without building

# Run all (docker)
docker-compose up --build
```

### Key Invariants to Preserve

**FAIR pipeline**
- `profile_csv()` must always return a `df` key; `main.py` and `entity_detector.py` depend on it.
- `session["columns"]` is a list of dicts, each with at least: `name`, `label`, `data_type`, `inferred_type`, `description`, `unit_guess`, `user_unit`, `missing_values`, `missing_pct`, `sample_values`. Adding keys is safe; renaming or removing breaks `fair_engine.py`, `export_engine.py`, and frontend state.
- The FAIR score is recomputed on every `GET /api/fair-score/{id}` call. Do not add a persistent cache without wiring invalidation to `PUT /columns` and `PUT /metadata`.
- Export endpoints stream responses directly; they do not write to disk.

**VCG pipeline**
- `session["vcg"]` must always be initialised from `DEFAULT_VCG_SESSION()` before any VCG endpoint writes to it. `_ensure_vcg(session)` in `vcg_router.py` handles this.
- `vcg_status` values are `not_started | running | done | failed`. The frontend polls for exactly these strings. Do not rename or add intermediate states without updating the polling logic in `VCGPage.tsx`.
- `run_vcg_pipeline` is synchronous and must be called via `asyncio.to_thread`. Do not make it async; the agents use blocking scipy/statsmodels calls.
- The VCG router receives `sessions`, `_save_session`, and `_load_session` by injection from `main.py`. It must not import from `main.py` directly (circular import).
- `session["df"]` must be present when `run_vcg_pipeline` is called. If loaded from SQLite, `_load_session` reconstructs it from `original_bytes` via `profile_csv`.

**Template layer**
- `session["template_id"]` is `str | None`. `session["template_validation"]` is the conformance report (list of entries). `session["template_candidates"]` is the ranked suggestion list. All three are initialised on upload; do not assume they exist on older sessions — guard with `.get()`.
- Conformance entries always have the shape `{standard, section, field_id, status, satisfied_by, severity, is_column_field}`. Adding fields is safe; renaming breaks frontend `ConformanceEntry` typing and the FAIR scorer.
- Template-derived issues use `category="template_compliance"` and id pattern `"template_{template_id}_{field_id}"`. The `DELETE /api/{id}/template` endpoint strips by this prefix — don't change the naming.
- Auto-assign threshold is **0.9**. Changing it requires updating `template_engine.suggest_templates` callers in `main.py:/api/upload` and the documented behaviour here.
- The template router uses the same `init_template_router(sessions, save_fn, load_fn)` injection as VCG. It must not import from `main.py`.
- Templates are loaded once at app startup. New user uploads via `POST /api/templates` must call `load_templates()` again (or invalidate cache) to be picked up by `suggest_templates`.
- `wizard-prefill` returns `template_locked: list[str]` and optionally `clustering_warning: str` when a template is assigned. The frontend reads these field names exactly; do not rename.
- `vcg_results["template_analyses"]` is appended only when the assigned template declares `predefined_analyses`. Each entry has `{id, type, status, description, result, error}`.
- `prepare_section`, `crosswalk`, and `satisfied_by.via_crosswalk` are additive — never remove these fields from conformance entries; frontend reads them by name.
- PREPARE field_ids use the `prepare_` prefix (e.g. `prepare_humane_endpoints`). ARRIVE field_ids do not. Don't unify them — the engine distinguishes them by id.
