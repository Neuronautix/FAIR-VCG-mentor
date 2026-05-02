# FAIR CSV Mentor — CLAUDE.md

## Project Overview

FAIR CSV Mentor is a web application that assesses CSV datasets against the [FAIR data principles](https://www.go-fair.org/fair-principles/) (Findable, Accessible, Interoperable, Reusable). Users upload a CSV, receive automated profiling and FAIR-readiness scoring, enrich metadata through a guided wizard, and export the result in standards-compliant formats (Frictionless DataPackage, CSVW, JSON-LD, RO-Crate).

---

## Repository Structure

```
FAIR-csv-mentor/
├── CLAUDE.md                 # This file
├── docker-compose.yml        # Orchestrates backend + frontend
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py               # FastAPI app, all REST endpoints
│   ├── csv_profiler.py       # Encoding/delimiter detection, column type & semantic inference
│   ├── fair_engine.py        # FAIR scoring (100-pt rubric) & issue detection
│   ├── entity_detector.py    # Table-shape inference (repeated measures, long/wide)
│   ├── uri_suggester.py      # Linked-data URI pattern generation
│   └── export_engine.py      # Multi-format export (CSV, CSVW, JSON-LD, RO-Crate, etc.)
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── App.tsx
        ├── api/client.ts         # Axios API client (maps to backend endpoints)
        ├── store/useStore.ts     # Zustand global state
        ├── components/
        │   ├── Layout.tsx
        │   ├── FAIRScoreBreakdown.tsx
        │   └── IssueCard.tsx
        └── pages/
            ├── UploadPage.tsx
            ├── OverviewPage.tsx
            ├── ColumnProfilePage.tsx
            ├── FAIRScorePage.tsx
            ├── MetadataWizardPage.tsx
            └── ExportPage.tsx
```

---

## Running the Project

```bash
# Start both services with live reload
docker-compose up

# Backend only (port 8000)
cd backend && pip install -r requirements.txt && uvicorn main:app --reload

# Frontend only (port 5173)
cd frontend && npm install && npm run dev
```

Backend API: `http://localhost:8000`  
Frontend: `http://localhost:5173`  
OpenAPI docs: `http://localhost:8000/docs`

---

## Architecture & Data Flow

```
User uploads CSV
      │
      ▼
POST /api/upload
  ├── csv_profiler.py   → detects encoding, delimiter, column types, semantic types
  ├── entity_detector.py → infers table shape, entity type, repeated measures
  └── fair_engine.py    → detects data quality issues
      │
      ▼
Session stored in-memory (UUID key)
      │
      ▼
User edits column metadata / fills dataset metadata wizard
      │
PUT /api/columns/{id}   → recalculates issues
PUT /api/metadata/{id}  → marks FAIR score dirty
      │
      ▼
GET /api/fair-score/{id}
  └── fair_engine.py    → scores F/A/I/R dimensions (25/20/30/25 pts)
      │
      ▼
GET /api/export/{id}/{type}
  └── export_engine.py  → generates cleaned-csv | data-dictionary | frictionless |
                          csvw | jsonld | report | rocrate
```

**Session model:** All state lives in a Python dict (`sessions: dict[str, SessionData]`). There is no database. Sessions are lost on restart.

---

## Backend Module Reference

### `main.py`
- All FastAPI route handlers
- In-memory session store (`sessions` dict)
- CORS configured for `localhost:5173` and `localhost:3000`
- Key routes:
  - `POST /api/upload` → profile + detect issues, return `dataset_id`
  - `GET /api/profile/{id}` → import info, columns, table structure
  - `GET /api/issues/{id}` → detected quality/metadata issues
  - `PUT /api/columns/{id}` → update column metadata, rerun issue detection
  - `GET|PUT /api/metadata/{id}` → dataset-level metadata
  - `GET /api/fair-score/{id}` → compute + return FAIR score
  - `GET /api/uris/{id}` → generate URI suggestions
  - `GET /api/export/{id}/{type}` → stream export file

### `csv_profiler.py`
- `profile_csv(file_bytes, filename)` → `ProfileResult`
- Detects: encoding (chardet), delimiter (csv.Sniffer), data types, semantic types, units
- Semantic type patterns: identifier, measurement, biological_descriptor, experimental_condition, time_variable, notes, metadata_field
- Returns column profiles with confidence scores, sample values, missing-value counts

### `fair_engine.py`
- `calculate_fair_score(session)` → `FAIRScore` with per-dimension breakdown
- `detect_issues(columns, import_info)` → `list[Issue]`
- FAIR rubric: F=25, A=20, I=30, R=25 points (5 pts per criterion)
- Issue severities: `high | medium | low`

### `entity_detector.py`
- `detect_entity_structure(columns, df)` → `TableStructure`
- Infers: primary entity, secondary entity, table shape, row representation
- Shape options: `one_row_per_entity | repeated_measures | repeated_measures_long_format | wide_measurement_format | tabular_data`

### `uri_suggester.py`
- `suggest_uris(session, base_uri)` → `URISuggestions`
- Generates: dataset URI, observation pattern, entity URIs, column URIs

### `export_engine.py`
- `generate_export(session, export_type)` → `(bytes, filename, content_type)`
- Export types: `cleaned-csv | data-dictionary | frictionless | csvw | jsonld | report | rocrate`

---

## Frontend Reference

### State (`store/useStore.ts`)
Central Zustand store. Key slices:
- `datasetId`, `importInfo`, `columns`, `tableStructure`
- `issues`, `fairScore`, `metadata`, `uriSuggestions`
- Actions: `setDatasetId`, `setColumns`, `updateColumn`, `setMetadata`, `setFairScore`

### API Client (`api/client.ts`)
Thin Axios wrapper. Exports one function per backend endpoint. Base URL is `/api` (proxied to port 8000 by Vite).

### Pages
| Page | File | Responsibility |
|------|------|----------------|
| Upload | `UploadPage.tsx` | File drag-drop, POST /upload, redirect to /overview |
| Overview | `OverviewPage.tsx` | Summary stats, table shape card, issues list |
| Column Profile | `ColumnProfilePage.tsx` | Editable table: label, description, type, units, vocab, URI |
| FAIR Score | `FAIRScorePage.tsx` | Score gauge + dimension breakdown + recommendations |
| Metadata Wizard | `MetadataWizardPage.tsx` | Dataset-level metadata form |
| Export | `ExportPage.tsx` | Per-format download buttons + RO-Crate bundle |

---

## Functionality & Usability Assessment

### What Works Well

**Core pipeline is solid.**
The automated analysis chain (profiling → issue detection → FAIR scoring → export) runs end-to-end without external dependencies. Semantic type inference uses domain-specific patterns (biology, clinical research) that are genuinely useful and cover most common CSV structures encountered in life-sciences data.

**Export coverage is comprehensive.**
Seven export formats cover the main interoperability standards relevant to FAIR data: Frictionless DataPackage, W3C CSVW, Schema.org JSON-LD, and RO-Crate. Few open-source tools provide all of these together.

**FAIR scoring is transparent.**
The 100-point rubric is deterministic and explainable — every score deduction maps to a specific missing metadata field or detectable structural problem. This makes it suitable as a teaching tool.

**UI is logically structured.**
The six-page wizard flow (Upload → Overview → Columns → Score → Metadata → Export) matches the natural user journey for FAIR compliance improvement.

**Docker deployment is straightforward.**
Single `docker-compose up` command starts both services with live-reload volumes, making local development quick.

---

### Usability Gaps

| Gap | Severity | Notes |
|-----|----------|-------|
| No persistence | High | Sessions are in-memory; refreshing the page or restarting the server loses all work. A user cannot save and return to a session. |
| No README | High | No getting-started guide, no description of what the tool does, no screenshots. Discovery is difficult for new contributors or users. |
| No tests | High | Zero test coverage across backend and frontend. Refactoring any core module carries high regression risk. |
| FAIR score not invalidated on column save | Medium | After `PUT /columns`, the score shown in the UI may be stale; the frontend does not automatically refetch `/fair-score`. |
| No input validation feedback | Medium | The upload endpoint accepts any file and fails silently on non-CSV content; error messages are not surfaced to the user. |
| Hardcoded patterns only | Medium | Semantic type and unit detection relies on column-name patterns. Unusual naming conventions score poorly with no fallback. |
| No pagination on column table | Low | Large CSVs (100+ columns) make `ColumnProfilePage` unwieldy. |
| CORS restricted to localhost | Low | Production deployment requires updating CORS origins manually in `main.py`. |
| openpyxl imported but unused | Low | Excel support is listed as a dependency but no Excel upload path exists. |

---

### Functionality Gaps

| Gap | Notes |
|-----|-------|
| No ontology lookup | Controlled vocabulary fields accept free text; no integration with OLS, BioPortal, or SKOS term search. |
| No diff/versioning | No way to compare FAIR score before and after metadata edits. |
| No batch processing | One file at a time; no API for processing multiple files or a directory. |
| Single-user only | No auth, no namespacing of sessions by user. |
| No validation of exported JSON-LD | Exported JSON-LD is not validated against Schema.org or SHACL shapes. |

---

## Multi-Agent Development Guidelines

This section defines how multiple Claude agents should collaborate on this codebase without conflicts.

### Ownership Boundaries

Each agent should work within a designated boundary. Avoid cross-boundary edits without explicit coordination.

| Domain | Files | Agent Role |
|--------|-------|------------|
| **Backend – Analysis** | `csv_profiler.py`, `entity_detector.py` | Improve semantic detection, add new column patterns, fix encoding edge cases |
| **Backend – Scoring** | `fair_engine.py` | Refine FAIR rubric, add/remove criteria, tune issue thresholds |
| **Backend – Export** | `export_engine.py`, `uri_suggester.py` | Add/fix export formats, validate against standards |
| **Backend – API** | `main.py` | Add endpoints, fix session logic, add persistence layer |
| **Frontend – Pages** | `pages/*.tsx` | UI layout, user flows, form behaviour |
| **Frontend – State** | `store/useStore.ts`, `api/client.ts` | State shape changes, API contract alignment |
| **Frontend – Components** | `components/*.tsx` | Shared UI components |
| **Testing** | `backend/tests/`, `frontend/src/__tests__/` | Write and run tests; no logic changes |
| **Docs & Config** | `CLAUDE.md`, `docker-compose.yml`, `requirements.txt`, `package.json` | Documentation, dependency updates |

### Coordination Rules

1. **One agent per boundary per session.** Do not have two agents editing `fair_engine.py` simultaneously.

2. **API contract is a shared interface.** Any agent changing a backend endpoint signature (`main.py`) or the Zustand store shape (`useStore.ts`) must also update the counterpart. State the contract change explicitly in the commit message.

3. **Session data shape is a coordination point.** The `sessions` dict structure in `main.py` is read by every backend module. If you change a field name or add a required key, grep for all usages and update them in the same commit.

4. **Do not change export format schemas silently.** Changes to Frictionless, CSVW, JSON-LD, or RO-Crate output in `export_engine.py` may break downstream consumers. Document schema changes in commit messages and, where possible, add a regression test.

5. **Prefer additive changes.** Add new semantic type patterns, scoring criteria, or export fields rather than replacing existing ones, until there is test coverage for the behaviour being replaced.

6. **Tests live alongside source.** Backend tests go in `backend/tests/`, frontend tests co-located as `*.test.tsx` or `*.test.ts`. Testing agents should not modify source files.

7. **Mark work-in-progress clearly.** If a task spans multiple commits (e.g. adding a persistence layer), open with a commit that adds a `# WIP` comment at the relevant entry point so other agents know the area is in flux.

### Suggested Parallel Task Decomposition

The following tasks are independent and safe to run in parallel:

| Task | Safe to run in parallel with |
|------|------------------------------|
| Add unit tests for `csv_profiler.py` | Any frontend task; `fair_engine.py` changes |
| Add unit tests for `fair_engine.py` | Any frontend task; `csv_profiler.py` changes |
| Add a README.md | Any task |
| Fix FAIR score invalidation on column save (frontend) | Any backend-only task |
| Add pagination to `ColumnProfilePage.tsx` | Any backend-only task |
| Add Excel upload support (backend) | Frontend pagination; README |
| Add ontology term search endpoint | Frontend column profile UI changes |

The following tasks have dependencies and must be serialised:

| Task | Must wait for |
|------|--------------|
| Add SQLite persistence | API endpoint review (session shape finalised) |
| Add auth/multi-tenancy | Persistence layer complete |
| Add SHACL validation for JSON-LD export | JSON-LD export format stabilised |
| Frontend ontology term picker | Backend ontology search endpoint |

### Commit Message Convention

```
<scope>: <imperative summary>

<optional body explaining why, not what>
```

Scope values: `backend`, `frontend`, `api`, `export`, `scoring`, `profiler`, `tests`, `docs`, `deps`, `config`

Examples:
```
scoring: add 5-pt criterion for machine-readable license URI
export: fix RO-Crate @context URL to use versioned spec
tests: add profiler tests for semicolon-delimited files
api: invalidate fair_score_cache on PUT /columns
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

- `profile_csv()` must always return a `dataframe` key in its result; `main.py` and `entity_detector.py` depend on it.
- `session["columns"]` is a list of dicts, each with at least `name`, `label`, `data_type`, `semantic_type`, `description`, `unit`, `missing_values`, `sample_values`. Adding new keys is safe; removing or renaming existing keys will break `fair_engine.py`, `export_engine.py`, and frontend state.
- The FAIR score is intentionally recomputed on every `GET /api/fair-score/{id}` call (no caching by default). Do not add a persistent cache without also wiring cache invalidation to `PUT /columns` and `PUT /metadata`.
- Export endpoints stream responses directly; they do not write to disk. Do not introduce temp-file side effects without cleanup logic.
