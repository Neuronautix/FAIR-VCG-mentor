# FAIR-VCG Mentor

A web application that assesses CSV datasets against the FAIR data principles and generates statistically rigorous Virtual Control Groups for pre-clinical research.

---

## What It Does

### FAIR Assessment

The [FAIR data principles](https://www.go-fair.org/fair-principles/) — Findable, Accessible, Interoperable, and Reusable — define a framework for publishing research data in a way that maximises its long-term value. In practice, most CSV files produced during research fall short of FAIR compliance: column names are ambiguous, units are undocumented, there is no machine-readable license, and the file ships with no accompanying metadata. Fixing these problems manually is tedious and requires familiarity with multiple standards.

FAIR-VCG Mentor automates the diagnostic step and provides a structured path to improvement. Upload a CSV and the tool immediately profiles every column — detecting encoding, delimiter, data types, semantic roles, and unit patterns — then scores the dataset against a 100-point FAIR rubric that maps each deduction to a specific, actionable issue. The scoring is fully transparent: every point lost corresponds to a named missing field or detectable structural problem.

The tool is particularly well-suited to life-sciences CSV datasets. Its semantic type inference covers patterns common in biology and clinical research: identifiers, measurements, biological descriptors, experimental conditions, time variables, and more.

### Virtual Control Group (VCG) Generation

A Virtual Control Group is a synthetic dataset that statistically replicates a concurrent vehicle/placebo cohort using only real historical control data. VCGs allow researchers to reduce the number of animals required per experiment while maintaining statistical power — a key component of the 3Rs framework (Replace, Reduce, Refine).

After the FAIR assessment, researchers configure a VCG through either a guided chat interface (rule-based AI assistant that asks about treatment columns, endpoints, covariates, and sample size) or a four-step wizard. The tool then runs an automated four-agent pipeline:

1. **Data Ingestion Agent** — validates the dataset and identifies control-group rows
2. **Standardisation Agent** — harmonises units and handles missing values
3. **VCG Builder Agent** — generates synthetic controls using a Gaussian copula bootstrap (N ≥ 15) or KDE/Normal sampling (N < 15), with optional covariate balancing
4. **Statistics Agent** — computes effect sizes, confidence intervals, and a reliability score

The pipeline produces a downloadable synthetic CSV and a Markdown statistical report including balance diagnostics.

---

## Quick Start

Requires [Docker](https://docs.docker.com/get-docker/) and Docker Compose.

```bash
git clone https://github.com/your-org/FAIR-vcg-mentor.git
cd FAIR-vcg-mentor
docker-compose up
```

Then open [http://localhost:5173](http://localhost:5173) in your browser.

The backend API is available at [http://localhost:8000](http://localhost:8000).
Interactive API documentation (OpenAPI / Swagger) is at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## Features

**FAIR assessment**
- Automated CSV profiling: encoding (chardet), delimiter, per-column data types, semantic types, units, missing-value counts, and sample values.
- 100-point FAIR rubric across four dimensions (F=25, A=20, I=30, R=25). Every deduction is tied to a specific, named issue.
- Issue detection with severity levels (high / medium / low) and actionable recommendations.
- Table-shape inference: one-row-per-entity, repeated measures, long-format, wide-format.
- Guided metadata enrichment wizard for dataset-level fields (title, description, license, creator, keywords, provenance).
- Editable column profiles: label, description, data type, units, vocabulary URI, semantic type.
- Linked-data URI suggestions for dataset, entities, observations, and columns.
- Seven standards-compliant export formats (see table below).

**VCG generation**
- Rule-based AI chat assistant that guides configuration through a natural conversation — no LLM API key required.
- Four-step wizard as an alternative to chat: research context, column roles, statistical config, review.
- Two generation methods: Gaussian copula bootstrap (preserves inter-endpoint correlations) and KDE/Normal synthetic sampling.
- Covariate balancing on biological descriptors (sex, strain, age).
- Configurable sample size (10–500 subjects) and confidence level.
- Downloadable VCG CSV and Markdown statistical report.

**Infrastructure**
- SQLite session persistence: sessions survive server restarts.
- No external service dependencies. All computation runs locally.
- Excel (.xlsx / .xls) upload supported alongside CSV.

---

## Workflow

### FAIR Assessment (steps 1–6)

1. **Upload.** Drag and drop a CSV or Excel file. The file is profiled immediately on the server.
2. **Overview.** Review summary statistics, the inferred table shape, and detected issues grouped by severity.
3. **Column Profile.** Inspect and edit every column's inferred metadata: label, description, data type, semantic type, units, and linked-data URI.
4. **FAIR Score.** See the overall score (0–100) broken down by Findable, Accessible, Interoperable, and Reusable dimensions, with per-criterion explanations and recommendations.
5. **Metadata Wizard.** Fill in dataset-level metadata. The FAIR score updates on the next visit to the score page.
6. **Export.** Download the enriched dataset in one or more supported formats.

### VCG Generation (steps 7–9)

7. **VCG Chat or Wizard.** Configure the VCG through the chat assistant (recommended for first-time users) or the four-step wizard (recommended when settings are already known). Both paths accept: treatment column, control group label, outcome columns, covariate columns, generation method, and sample size.
8. **Generation.** The four-agent pipeline runs asynchronously. A status bar cycles through agent names while work proceeds.
9. **Results & Export.** Review the reliability score, balance diagnostics, and per-endpoint statistics. Download the synthetic CSV or the full Markdown statistical report.

---

## Export Formats

| Format | File | Standard |
|--------|------|----------|
| Cleaned CSV | `cleaned_data.csv` | — |
| Data Dictionary | `data_dictionary.csv` | — |
| Frictionless DataPackage | `datapackage.json` | [Frictionless Data](https://specs.frictionlessdata.io/) |
| W3C CSVW | `csvw_metadata.json` | [W3C CSV on the Web](https://www.w3.org/TR/tabular-data-primer/) |
| JSON-LD | `metadata.jsonld` | [Schema.org](https://schema.org/) |
| FAIR Report | `fair_readiness_report.md` | — |
| RO-Crate | `ro-crate.zip` | [RO-Crate 1.2](https://www.researchobject.org/ro-crate/) |
| VCG CSV | `virtual_control_group.csv` | — |
| VCG Statistical Report | `vcg_statistical_report.md` | — |

---

## Development Setup

### Backend

Python 3.9+ is required.

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend

Node.js 18+ is required.

```bash
cd frontend
npm install
npm run dev          # starts dev server at http://localhost:5173
npm run type-check   # TypeScript checks without building
```

The Vite dev server proxies `/api` requests to the backend. When running outside Docker set `VITE_BACKEND_URL` (see below) or leave it unset to default to `http://localhost:8000`.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_DB` | `sessions.db` | Path to the SQLite session database |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | Comma-separated list of allowed CORS origins |
| `VITE_BACKEND_URL` | `http://localhost:8000` | Backend URL used by the Vite proxy. Set to `http://backend:8000` when running in Docker Compose so the frontend container can reach the backend service by name. |

---

## Architecture

The backend is a **FastAPI** application (Python). On upload, three modules run in sequence: `csv_profiler.py` handles encoding and type detection, `entity_detector.py` infers table shape, and `fair_engine.py` detects issues. Session state is persisted to SQLite (keyed by UUID) and also held in memory for the lifetime of the process. Export responses are streamed directly to the client.

The VCG pipeline lives in the `vcg/` package. The `vcg_router.py` FastAPI router exposes chat, wizard, generation, status, and export endpoints under `/api/vcg/{dataset_id}/`. The `orchestrator.py` implements a finite-state rule-based conversation engine (no LLM required). `vcg_engine.py` runs the four agents synchronously inside `asyncio.to_thread`, updating the session on completion.

The frontend is a **React/TypeScript** single-page application built with Vite. Global state is managed by Zustand. An Axios client in `api/client.ts` maps one-to-one onto backend endpoints.

---

## Repository Structure

```
FAIR-vcg-mentor/
├── docker-compose.yml
├── backend/
│   ├── main.py               # FastAPI app, all REST endpoints
│   ├── csv_profiler.py       # Encoding/delimiter detection, column type & semantic inference
│   ├── fair_engine.py        # FAIR scoring (100-pt rubric) & issue detection
│   ├── entity_detector.py    # Table-shape inference
│   ├── uri_suggester.py      # Linked-data URI generation
│   ├── export_engine.py      # Multi-format export
│   └── vcg/
│       ├── vcg_router.py     # FastAPI router — all /api/vcg/* endpoints
│       ├── orchestrator.py   # Rule-based chat engine (finite-state machine)
│       ├── vcg_engine.py     # Four-agent pipeline orchestrator
│       ├── vcg_wizard.py     # Wizard payload validation
│       ├── context_model.py  # Data model: ResearchContext, ColumnRoles, VCGConfig
│       ├── vcg_report.py     # Markdown statistical report generator
│       ├── constants.py      # Control-group keyword list
│       ├── agents/
│       │   ├── ingestion_agent.py      # Data validation & control-row extraction
│       │   ├── standardization_agent.py # Unit harmonisation & missing-value handling
│       │   ├── vcg_bootstrap.py        # Gaussian copula bootstrap (N ≥ 15)
│       │   ├── vcg_synthetic.py        # KDE/Normal sampling (N < 15)
│       │   └── stats_agent.py          # Effect sizes, CIs, reliability score
│       └── utils/
│           ├── covariate_balance.py    # Balance diagnostics
│           └── distributions.py       # Distribution fitting helpers
└── frontend/
    └── src/
        ├── api/client.ts     # Axios API client
        ├── store/useStore.ts # Zustand global state
        ├── components/       # Shared UI components
        └── pages/
            ├── UploadPage.tsx
            ├── OverviewPage.tsx
            ├── ColumnProfilePage.tsx
            ├── FAIRScorePage.tsx
            ├── MetadataWizardPage.tsx
            ├── ExportPage.tsx
            ├── VCGPage.tsx         # Chat interface + generation status polling
            ├── VCGWizardPage.tsx   # Four-step configuration wizard
            └── VCGResultsPage.tsx  # Results, diagnostics, export
```

---

## Priority Punch List

Items needed before the tool is used in a real study, followed by quality-of-life improvements. These supplement the long-form roadmap below.

### Must Have

- [ ] **Test suite — zero coverage is a critical risk.** `vcg_bootstrap.py`, `vcg_synthetic.py`, `stats_agent.py`, and `csv_profiler.py` do statistical computation with no tests. Any refactor of these files carries silent regression risk. Add `backend/tests/` with at least happy-path and edge-case (N=5, high CV, all-missing column) scenarios. `[credibility]`
- [ ] **VCG type-mismatch guard.** Control-group matching uses `df[treatment_col] == control_value` with string equality. If the column is numeric (`int64`, `float64`), the comparison silently produces an empty control set and the pipeline fails without a clear error. Add a type-aware equality check (or coerce to string before matching) in `ingestion_agent.py`. `[credibility]`
- [ ] **Server-side PDF size enforcement.** The 32 MB guard lives inside `paper_extractor.py` but the full file is already in memory by then. Add `Content-Length` rejection (or post-read length check) at the FastAPI layer in `main.py` before calling `extract_paper_metadata`, so large uploads fail fast with a clear 413 response rather than OOM. `[usability]`
- [ ] **Frontend error boundary.** An unhandled exception in any page component (e.g., from a null-dereference on unexpected API shape) silently white-screens the app with no recovery path. Wrap `<App>` in a React error boundary that shows a "Something went wrong — reload" message. `[usability]`
- [ ] **Persist VCG conversation to SQLite.** Reloading the VCG Chat page loses the entire conversation; the user must restart from the beginning. The session model already supports arbitrary keys; add `vcgConversation` serialisation to `_save_session`. `[usability]`

### Nice to Have

- [ ] **DOI format validation.** Validate the DOI field before sending to the backend (a simple `10.\d{4,}/.+` regex on the client). Currently any string is sent and a 400 is returned with a CrossRef error message that is not user-friendly. `[usability]`
- [ ] **Streaming elapsed-time counter.** Show elapsed seconds next to the status message during PDF extraction (e.g., "Extracting study metadata… 14 s"). Reduces perceived wait time and signals the page is not frozen. `[usability]`
- [ ] **Paper import re-run without losing CSV session.** Clicking "Import Different Paper" on `PaperImportPage` clears `paperExtraction` but keeps the dataset loaded. Currently clearing extraction does not remove the persisted SQLite extraction, so the old one is restored on next page visit. Call `DELETE /api/paper/{id}/extraction` (new endpoint needed) when the user clears. `[usability]`
- [ ] **"From paper" badges persist after Metadata Wizard save.** The `paperFilledFields` set lives in local React state and is lost on page reload. Store it in the Zustand `paperExtraction` slice or derive it by comparing saved metadata against extraction values on mount. `[usability]`
- [ ] **LLM FAIR score auto-trigger.** If the rule-based score is below 50 and `ANTHROPIC_API_KEY` is configured, show the "Get AI Assessment" button as a primary CTA rather than a secondary option. `[usability]`
- [ ] **Ontology term lookup for column vocabulary.** The URI field in Column Profile accepts free text. Integrate a lightweight OLS or BioPortal search (debounced autocomplete) so researchers can attach real ontology terms rather than lab-internal strings. Required for machine-readable interoperability at the field level. `[usability]`
- [ ] **Diff view for FAIR score before/after metadata edit.** Show +/- point changes when the user returns to the score page after filling in the Metadata Wizard, so the impact of each field is visible. `[usability]`

### Vocabulary, HITL & schema verification (follow-ups)

Follow-ups to the controlled vocabulary + HITL system landed in PR #4. The base layer (versioned vocabulary, enum-constrained tool inputs, cached schema system block, schema_version stamping, PDF discovery) is in place; these items tighten the loop.

- [ ] **Structural schema verification pre-flight on validate.** Before flipping `vocabulary.validated = True`, run a structural check (unit fragments that don't parse, duplicate semantic-type assignments, columns with no role, controlled-value sets that overlap with declared identifiers). Surface findings inline and require an override for any blocking finding. `[credibility]`
- [ ] **Per-field vocabulary templates.** Let users save vocabulary subsets as named templates (`pharmacology_units`, `arrive_metadata_keys`, `oncology_study_types`, …) and re-apply them to fresh sessions. Hooks into the existing `template_store.py` signature-based matching. `[usability]`
- [ ] **OLS / BioPortal lookup for ontology IRIs.** Replace free-text vocabulary extensions with proposed IRIs drawn from EFO / UO / NCIT / CHEBI. HITL `schema_extension` suggestions then carry both the term and its canonical IRI so downstream FAIR exports can link out. Biggest single FAIR-interoperability win. `[credibility]` `[usability]`
- [ ] **Vocabulary diff view.** Render the `vocabulary.history` entries on the Vocabulary panel so users can see what each version added/removed and why (init, user_validate, hitl_apply, etc.). Foundation for the audit trail required by regulatory reviewers. `[credibility]`
- [ ] **Text-mode discovery.** Wire a "scan dataset description / methods" mode in `llm_vocab_discovery.discover_from_text` and expose it via `POST /api/llm/{id}/discover-vocab/from-text`. Removes the PDF dependency for users who only have a methods paragraph. `[usability]`
- [ ] **Auto-stale on column edit.** When `PUT /api/columns/{id}` adds new sample values or renames a controlled-value entry, auto-bump `vocabulary.version` and mark older HITL suggestions stale. Currently the bump only fires on explicit validate / schema_extension approval. `[credibility]`
- [ ] **In-place re-suggestion for stale cards.** Add a "Regenerate against v{N}" action on stale HITL cards that re-runs the originating LLM call against the latest vocabulary, replacing the stale suggestion with a fresh one. Removes the need to retrigger from each origin page. `[usability]`

---

## Roadmap

The goal is to make FAIR-VCG Mentor a credible scientific instrument that genuinely reduces animal numbers in pre-clinical research — not just a useful tool, but one that an ethics committee, a journal reviewer, or a regulatory authority can point to. Items are grouped by time horizon and tagged by primary benefit: **[animal reduction]**, **[credibility]**, or **[usability]**.

### Paper import & LLM enrichment

- [x] **Auto-apply paper extraction on CSV upload** — if a paper was imported before uploading the CSV, automatically pre-fill session metadata with no extra clicks. `[usability]`
- [x] **Metadata Wizard: pre-fill from paper** — pre-populate form fields from extracted paper metadata with visible "from paper" badges so users review and confirm rather than re-type. `[usability]`
- [x] **VCG Wizard: paper-hint column suggestions** — highlight outcome and covariate chips that match paper-hinted endpoint names; pre-fill control group label from paper. `[usability]`
- [x] **Column Profile: paper match badges** — mark columns matching paper-hinted endpoint or covariate names with a visual indicator. `[usability]`
- [x] **Persist paper extraction to SQLite** — store the extraction result in the session so it survives a page reload. `[usability]`
- [x] **Structured output via Anthropic tool_use** — replace JSON-from-text parsing in paper_extractor with guaranteed structured output via the tools API, eliminating parse-error edge cases. `[credibility]`
- [x] **Streaming extraction response** — SSE endpoint with live status ticks every 7 s; status messages cycle indefinitely for slow extractions. `[usability]`
- [x] **CrossRef DOI lookup** — accept a DOI as an alternative to PDF upload; fetch bibliographic metadata from CrossRef (free, no LLM required) as a fast path for published papers. `[usability]`
- [x] **LLM-powered FAIR scoring** — supplement the rule-based rubric with a Claude qualitative assessment that judges whether descriptions are genuinely informative, whether keywords are relevant, and whether ARRIVE fields are substantively complete rather than just present. `[credibility]`

### Short term

Improvements to what already exists.

- [x] **VCG suitability gate** — refuse or warn loudly before generation when conditions are not met: too few controls (n < 6), high between-subject CV, presence of outliers that inflate variance, or non-overlapping control/treatment distributions. A clear rejection is more trustworthy than a low reliability score. `[credibility]`
- [x] **Reliability score breakdown** — replace the single 0–1 number with a per-endpoint table: KS divergence, Cohen's d, CI width, and a plain-English interpretation of each. Give scientists the language they need for a methods section or supplementary material. `[credibility]`
- [x] **Diagnostic plots in results** — side-by-side density plots (real control vs VCG) and Q-Q plots per endpoint, rendered in the VCG Results page and included in the Markdown export. A score alone will not satisfy a statistical reviewer. `[credibility]`
- [x] **Expose method diagnostics** — show which marginal distribution (Normal / LogNormal / Gamma) was fitted to each column, the fit quality (AIC/BIC), and bootstrap convergence. Scientists must be able to audit and report the method, not just accept auto-selection. `[credibility]`
- [x] **ARRIVE 2.0 compliance checker** — flag missing ARRIVE 2.0 items in uploaded metadata. ARRIVE is required by most journals for in vivo papers; integrating the check positions the tool inside a workflow researchers already have. `[usability]`
- [x] **Test suite** — unit tests for `vcg_bootstrap.py`, `vcg_synthetic.py`, `stats_agent.py`, and `csv_profiler.py`. Zero test coverage is the main barrier to safe iteration on statistical code. `[credibility]`

### Medium term

Architectural additions that substantially increase scientific value.

- [ ] **Multi-study historical control database** — allow users to register multiple past studies as a lab-specific pool; VCG generation draws from this pool rather than a single concurrent study. This is how published VCG methodology (Friede & Kieser, Wandel et al.) actually works. Without it the tool is a proof-of-concept. `[animal reduction]` `[credibility]`
- [ ] **Control drift detection** — when a historical pool exists, automatically test whether current controls are statistically consistent with historical ones (Levene test for variance homogeneity, ANOVA for mean drift over time). Warn before pooling data from drifted cohorts. `[credibility]`
- [ ] **Pre-experiment study design advisor** — given a historical pool, answer: "how many concurrent control animals do I need to achieve reliability ≥ X for these endpoints?" Requires bootstrapping historical data at decreasing concurrent-control n. This is the primary animal-reduction lever. `[animal reduction]`
- [ ] **Bayesian pooling option** — treat concurrent controls as a likelihood update on a prior derived from historical data, rather than pooling raw rows. More principled for small concurrent n and directly mirrors EMA's reflection paper on acceptable use of historical control data. `[credibility]`
- [ ] **SEND-compatible export** — generate FDA-required SEND domains (BW for body weight, CL for clinical pathology) from profiled data. Makes the tool relevant to CROs and pharma companies preparing regulatory submissions. `[credibility]` `[usability]`
- [ ] **Ontology term lookup** — integrate OLS or BioPortal search for controlled vocabulary fields instead of free-text input. Required for machine-readable FAIR interoperability. `[usability]`

### Long term

Impact and field positioning.

- [ ] **Publish a validation study** — hold out concurrent controls from 20–30 real studies, generate VCGs, measure how well they would have substituted. Report sensitivity/specificity for detecting true treatment effects and false-positive rate. Submit to *Toxicological Sciences* or *Regulatory Toxicology and Pharmacology*. Without peer-reviewed validation no ethics committee will formally accept "we used a VCG." `[credibility]`
- [ ] **NC3Rs / EURL ECVAM assessment** — submit the tool for formal evaluation by the [NC3Rs](https://www.nc3rs.org.uk) (UK) or [EURL ECVAM](https://ec.europa.eu/jrc/en/eurl/ecvam) (EU). Endorsement by either body provides regulatory credibility that software polish cannot. Both organisations also have direct lines to FDA and EMA. `[credibility]` `[animal reduction]`
- [ ] **Regulatory alignment document** — map the tool's methodology explicitly to FDA M3(R2) and EMA reflection paper on historical control data. State clearly what is covered and what is not. Gives regulatory affairs teams something concrete to include in a submission dossier. `[credibility]`
- [ ] **Federated historical control sharing** — privacy-preserving pooling of summary statistics or model parameters across labs, enabling VCG generation for labs with small individual datasets. Technically hard (differential privacy, federation infrastructure) but would make the tool genuinely field-wide rather than lab-specific. `[animal reduction]`
- [ ] **Persist VCG conversation to SQLite** — reload chat history on page refresh so users can return to a session without losing context. `[usability]`
- [ ] **Multi-user support with authentication** — session namespacing per user, required for any institutional or shared deployment. `[usability]`

---

## Contributing

Contributions are welcome. This project uses a multi-agent development model with explicit ownership boundaries for each module group. Before making changes, read [CLAUDE.md](./CLAUDE.md) for the full coordination rules, commit message conventions, key invariants to preserve, and guidance on which tasks are safe to work on in parallel.

In brief: prefer additive changes over replacements, keep API contract changes atomic across both backend and frontend, and add tests for any behaviour you intend to modify.

### Open-source release check

Run the global release-readiness audit before sharing or tagging a release:

```bash
python scripts/oss_readiness_check.py --strict
```

This verifies required project files and policies, license declarations, README structure, frontend metadata, and CI workflow coverage.

---

## License

GNU GPL v3.0 — see [LICENSE](./LICENSE).
