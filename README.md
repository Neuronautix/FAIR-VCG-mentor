# FAIR CSV Mentor — Demo

A focused web application for FAIR dataset assessment, ARRIVE 2.0 reporting completeness,
and PREPARE study planning readiness. Designed for life-sciences researchers working with
tabular CSV/Excel data.

## What this does

- **Upload and profile** CSV and Excel files — detects encoding, delimiter, column types,
  semantic types, units, and missing values automatically.

- **FAIR readiness score** — rules-based assessment across the four FAIR dimensions
  (Findable, Accessible, Interoperable, Reusable), with concrete recommendations.

- **ARRIVE 2.0 reporting completeness** — checks whether your dataset metadata addresses
  the ARRIVE 2.0 reporting guidelines (arriveGuidelines.org). This is a completeness
  assessment, not a quality validation.

- **PREPARE study planning readiness** — checks whether the PREPARE pre-study planning
  checklist items (Smith AJ et al., Lab Anim 2018) are addressed. This is a planning
  readiness assessment, not regulatory validation.

- **Metadata enrichment wizard** — guided form for dataset-level metadata (title,
  description, creator, species, license, etc.) that directly improves your FAIR score.

- **Template selector** — assign the ARRIVE 2.0 or PREPARE template (or the combined
  crosswalk) to unlock conformance reports.

- **Paper import** — extract metadata from a PDF paper (requires Anthropic API key on
  the server) to pre-fill the metadata wizard.

- **Exports** — cleaned CSV, data dictionary, FAIR-readiness report, ARRIVE conformance
  report, PREPARE readiness report (all Markdown or CSV).

- **Optional AI suggestions** (user-provided OpenAI key) — suggest improvements to
  dataset metadata and column descriptions. Raw data rows are never sent to OpenAI.
  A preview of exactly what will be sent is shown before each API call. The key is
  stored only in server RAM and cleared on restart.

## What this does NOT do

This demo does not include Virtual Control Group (VCG) generation, synthetic cohort
statistics, or linked-data export formats (JSON-LD, RO-Crate, CSVW, Frictionless).

## Running locally

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
API docs: `http://localhost:8000/docs`

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `SESSION_DB` | `sessions.db` | SQLite database path |
| `CORS_ORIGINS` | localhost origins | Allowed CORS origins (comma-separated) |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model for AI suggestions |
| `MAX_UPLOAD_MB` | `32` | Maximum upload file size in MB |
| `ENVIRONMENT` | `development` | Set to `production` to suppress stack traces |

## Running tests

```bash
cd backend
pip install -r requirements.txt pytest
pytest tests/ -v
```

## Deploying to GCE VM

See [docs/DEPLOY_GCE_VM.md](docs/DEPLOY_GCE_VM.md) for complete GCE deployment instructions.

## Architecture

- **Backend:** FastAPI + Python, SQLite session persistence, scipy-based profiling
- **Frontend:** React + TypeScript + Vite + MUI
- **Production:** Nginx (static), Caddy (TLS termination + proxy), Docker Compose

## Disclaimer

This tool provides FAIR-readiness, ARRIVE 2.0, and PREPARE assessments for educational
and self-improvement purposes. It does not constitute regulatory certification, legal
compliance advice, or proof of research quality.
