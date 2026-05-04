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

## Roadmap

The goal is to make FAIR-VCG Mentor a credible scientific instrument that genuinely reduces animal numbers in pre-clinical research — not just a useful tool, but one that an ethics committee, a journal reviewer, or a regulatory authority can point to. Items are grouped by time horizon and tagged by primary benefit: **[animal reduction]**, **[credibility]**, or **[usability]**.

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

---

## License

GNU GPL v3.0 — see [LICENSE](./LICENSE).
