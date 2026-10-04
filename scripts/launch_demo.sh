#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

uv sync --frozen
exec bash scripts/run_website.sh \
  --db data/fireatlas.sqlite3 \
  --host 127.0.0.1 \
  --port "${PORT:-8000}"
