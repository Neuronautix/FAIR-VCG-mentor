# FAIR CSV Mentor

A web application that assesses CSV datasets against the FAIR data principles and guides researchers through metadata enrichment and standards-compliant export.

---

## What It Does

The [FAIR data principles](https://www.go-fair.org/fair-principles/) — Findable, Accessible, Interoperable, and Reusable — define a framework for publishing research data in a way that maximises its long-term value. In practice, most CSV files produced during research fall short of FAIR compliance: column names are ambiguous, units are undocumented, there is no machine-readable license, and the file ships with no accompanying metadata. Fixing these problems manually is tedious and requires familiarity with multiple standards.

FAIR CSV Mentor automates the diagnostic step and provides a structured path to improvement. Upload a CSV and the tool immediately profiles every column — detecting encoding, delimiter, data types, semantic roles, and unit patterns — then scores the dataset against a 100-point FAIR rubric that maps each deduction to a specific, actionable issue. The scoring is fully transparent: every point lost corresponds to a named missing field or detectable structural problem, making the tool suitable as both a practical aid and a teaching instrument.

The tool is particularly well-suited to life-sciences CSV datasets. Its semantic type inference covers patterns common in biology and clinical research: identifiers, measurements, biological descriptors, experimental conditions, time variables, and more. After reviewing the automated analysis, researchers enrich the dataset metadata through a guided wizard and download the result in any of seven standards-compliant formats, including Frictionless DataPackage, W3C CSVW, Schema.org JSON-LD, and RO-Crate.

---

## Quick Start

Requires [Docker](https://docs.docker.com/get-docker/) and Docker Compose.

```bash
git clone https://github.com/your-org/FAIR-csv-mentor.git
cd FAIR-csv-mentor
docker-compose up
```

Then open [http://localhost:5173](http://localhost:5173) in your browser.

The backend API is available at [http://localhost:8000](http://localhost:8000).  
Interactive API documentation (OpenAPI / Swagger) is at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## Features

- **Automated CSV profiling.** Detects encoding (via chardet), delimiter, per-column data types, semantic types, units, missing-value counts, and sample values. No configuration required.
- **FAIR-readiness scoring.** A 100-point rubric across the four FAIR dimensions (F=25, A=20, I=30, R=25). Every deduction is tied to a specific, named issue so you know exactly what to fix.
- **Issue detection.** Data quality and metadata issues are classified by severity (high / medium / low) and displayed with actionable recommendations.
- **Table-shape inference.** Automatically identifies whether the data is one-row-per-entity, repeated measures, long-format, wide-format, or general tabular, and surfaces this in the overview.
- **Metadata enrichment wizard.** A guided form for dataset-level metadata: title, description, creator, license, subject, keywords, temporal and spatial coverage, and controlled vocabulary references.
- **Editable column profiles.** Review and correct every column's label, description, data type, units, vocabulary URI, and semantic type.
- **Seven export formats.** Download the enriched dataset and metadata in the format most appropriate for your repository or downstream tool (see table below).
- **Linked-data URI suggestions.** Generates URI patterns for the dataset, observations, entities, and columns to support linked-data publication.
- **No external dependencies.** The full analysis pipeline runs locally. No API keys, no internet connection required after installation.

---

## The Six-Step Workflow

1. **Upload.** Drag and drop a CSV file (or click to browse). The file is profiled immediately on the server.
2. **Overview.** Review summary statistics, the inferred table shape, and the list of detected issues grouped by severity.
3. **Column Profile.** Inspect and edit every column's inferred metadata: label, description, data type, semantic type, units, and linked-data URI.
4. **FAIR Score.** See the overall score (0–100) broken down by Findable, Accessible, Interoperable, and Reusable dimensions, with per-criterion explanations and recommendations.
5. **Metadata Wizard.** Fill in dataset-level metadata fields. The FAIR score updates when you return to the score page.
6. **Export.** Download the enriched dataset in one or more of the supported formats.

---

## Export Formats

| Format | File | Standard |
|--------|------|----------|
| Cleaned CSV | `cleaned_data.csv` | - |
| Data Dictionary | `data_dictionary.csv` | - |
| Frictionless DataPackage | `datapackage.json` | [Frictionless Data](https://specs.frictionlessdata.io/) |
| W3C CSVW | `csvw_metadata.json` | [W3C CSV on the Web](https://www.w3.org/TR/tabular-data-primer/) |
| JSON-LD | `metadata.jsonld` | [Schema.org](https://schema.org/) |
| FAIR Report | `fair_readiness_report.md` | - |
| RO-Crate | `ro-crate.zip` | [RO-Crate 1.2](https://www.researchobject.org/ro-crate/) |

---

## Development Setup

### Backend

Python 3.9+ is required.

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000` with auto-reload on file changes.

### Frontend

Node.js 18+ is required.

```bash
cd frontend
npm install
npm run dev          # starts dev server at http://localhost:5173
npm run type-check   # run TypeScript checks without building
```

The Vite dev server proxies `/api` requests to the backend at port 8000, so both services must be running for the full application to work.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_DB` | `sessions.db` | Path to the SQLite session database (when persistence is enabled) |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | Comma-separated list of allowed CORS origins for production deployments |

---

## Architecture

The backend is a **FastAPI** application (Python) that exposes a REST API. On upload, three modules run in sequence: `csv_profiler.py` handles encoding and type detection, `entity_detector.py` infers table shape, and `fair_engine.py` detects issues and computes the FAIR score. Session state is held in an in-memory Python dict keyed by a UUID; there is no database in the default configuration. Export responses are streamed directly to the client without writing temporary files to disk.

The frontend is a **React/TypeScript** single-page application built with Vite. Global state is managed by Zustand. An Axios client in `api/client.ts` maps one-to-one onto backend endpoints. The six pages correspond to the six workflow steps above.

There are no external service dependencies. All computation runs locally.

---

## Repository Structure

```
FAIR-csv-mentor/
├── docker-compose.yml
├── backend/
│   ├── main.py               # FastAPI app, all REST endpoints
│   ├── csv_profiler.py       # Encoding/delimiter detection, column type & semantic inference
│   ├── fair_engine.py        # FAIR scoring (100-pt rubric) & issue detection
│   ├── entity_detector.py    # Table-shape inference
│   ├── uri_suggester.py      # Linked-data URI generation
│   └── export_engine.py      # Multi-format export
└── frontend/
    └── src/
        ├── api/client.ts     # Axios API client
        ├── store/useStore.ts # Zustand global state
        ├── components/       # Shared UI components
        └── pages/            # One file per workflow step
```

---

## Contributing

Contributions are welcome. This project uses a multi-agent development model with explicit ownership boundaries for each module group (backend analysis, backend scoring, backend export, API layer, frontend pages, frontend state, testing, and docs). Before making changes, read [CLAUDE.md](./CLAUDE.md) for the full coordination rules, commit message conventions, key invariants to preserve, and guidance on which tasks are safe to work on in parallel.

In brief: prefer additive changes over replacements, keep API contract changes atomic across both backend and frontend, and add tests for any behaviour you intend to modify.

---

## License

MIT — see [LICENSE](./LICENSE).
