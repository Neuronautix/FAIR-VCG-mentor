#!/bin/bash
# SessionStart hook — repairs the FastAPI install and installs deps so the
# backend test suite and frontend type-check work immediately in web sessions.
set -euo pipefail

# Only run in Claude Code on the web (remote env); no-op for local CLI sessions.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

"$CLAUDE_PROJECT_DIR/scripts/setup_env.sh"
