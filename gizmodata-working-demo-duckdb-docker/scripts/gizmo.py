"""Shared connection config for the GizmoSQL demo scripts.

Credentials are read from environment variables or an optional `.env`
file at the project root -- never hardcoded in source. Copy
`.env.example` to `.env` to set the local dev defaults.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path=None):
    """Minimal KEY=VALUE loader (stdlib only, no dependency)."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def conn_args():
    load_dotenv()
    missing = [k for k in ("GIZMOSQL_USERNAME", "GIZMOSQL_PASSWORD")
               if not os.environ.get(k)]
    if missing:
        raise RuntimeError(
            f"Missing env var(s): {', '.join(missing)}. "
            "Copy .env.example to .env or export them."
        )
    return dict(
        uri=os.environ.get("GIZMOSQL_URI", "gizmosql://localhost:31337"),
        username=os.environ["GIZMOSQL_USERNAME"],
        password=os.environ["GIZMOSQL_PASSWORD"],
        tls_skip_verify=os.environ.get("GIZMOSQL_TLS_SKIP_VERIFY", "1") == "1",
    )
