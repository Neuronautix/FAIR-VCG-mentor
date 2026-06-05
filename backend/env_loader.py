import os
from pathlib import Path


def load_local_env() -> None:
    """Load simple KEY=VALUE pairs from local .env files without overriding env vars."""
    backend_dir = Path(__file__).resolve().parent
    for env_path in (backend_dir.parent / ".env", backend_dir / ".env"):
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and key not in os.environ:
                os.environ[key] = value
