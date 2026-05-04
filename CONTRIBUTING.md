# Contributing to FAIR-VCG Mentor

Thank you for contributing.

## Before You Start

- Read CLAUDE.md for architecture boundaries, invariants, and commit scope guidance.
- Open an issue for large changes so maintainers can align on approach.
- Keep changes focused and include tests when behavior changes.

## Local Setup

### Backend

```bash
cd backend
pip install -r requirements.txt
pip install pytest
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Validation Checklist

Run these checks before opening a pull request:

```bash
python scripts/oss_readiness_check.py --strict
pytest backend/tests -q
cd frontend && npm run type-check && npm run build
```

## Pull Request Guidelines

- Use clear commit messages with scope prefix (for example: backend, frontend, vcg, tests, docs).
- Update documentation when API contracts or behavior change.
- Include screenshots for visible UI changes.
- Keep PR descriptions explicit: what changed, why, and how it was validated.

## Code Style

- Prefer small, additive changes over wide refactors.
- Preserve existing API contracts unless the change requires a coordinated update.
- Add concise comments only when logic is non-obvious.

## Reporting Issues

If you find a bug or documentation gap, open an issue with:

- expected behavior
- actual behavior
- repro steps
- sample file or payload (if possible)
