#!/bin/bash
# Prepare the environment so the backend test suite and frontend type-check run cleanly.
#
# Safe to run repeatedly (idempotent) and usable both by the SessionStart hook
# (Claude Code on the web) and by CI / local setup.
#
# The load-bearing part is the FastAPI repair: some base images ship a stray
# `fastapi/_compat/` package directory (from a different FastAPI version) that
# shadows the pinned 0.115.0 `fastapi/_compat.py` module. Python then imports the
# package, which lacks `PYDANTIC_V2`, so `import fastapi` fails with
# "cannot import name 'PYDANTIC_V2'" and every router/integration test errors at
# collection. Removing the stray shadow restores a consistent install.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ── Backend dependencies ────────────────────────────────────────────────────
echo "[setup] installing backend dependencies…"
pip install -q -r "$ROOT/backend/requirements.txt" \
  || echo "[setup] WARN: pip install failed (continuing; deps may already be present)"

# ── Repair corrupted FastAPI install ────────────────────────────────────────
# Locate site-packages WITHOUT importing fastapi (it may be broken at this point).
SITE="$(python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
FASTAPI_DIR="$SITE/fastapi"
if [ -f "$FASTAPI_DIR/_compat.py" ] && [ -d "$FASTAPI_DIR/_compat" ]; then
  echo "[setup] removing stray fastapi/_compat/ shadow package…"
  rm -rf "$FASTAPI_DIR/_compat"
fi

if ! python -c "import fastapi" >/dev/null 2>&1; then
  echo "[setup] fastapi still not importable — force-reinstalling fastapi==0.115.0…"
  pip install -q --force-reinstall --no-deps "fastapi==0.115.0" \
    || echo "[setup] WARN: force-reinstall failed (offline?)"
fi

python -c "import fastapi, pydantic; print(f'[setup] fastapi {fastapi.__version__} + pydantic {pydantic.__version__} OK')"

# ── Frontend dependencies (enables `npm run type-check`) ────────────────────
# Only when missing, so cached containers start instantly.
if [ -f "$ROOT/frontend/package.json" ] && [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "[setup] installing frontend dependencies…"
  (cd "$ROOT/frontend" && npm install --no-audit --no-fund --silent) \
    || echo "[setup] WARN: npm install failed (continuing)"
fi

echo "[setup] done."
