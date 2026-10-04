#!/usr/bin/env bash
# Start the real website with the installed assistant runtime and private config.
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$project_root"
# Existing observations stay as they are. A fresh checkout can seed the bundled
# authentic sample through the server's normal first-launch behavior.
website_args=()
if [[ -f data/fireatlas.sqlite3 ]]; then
  website_args+=(--no-showcase)
fi
if [[ -f .env.assistant ]]; then
  if [[ ! -x .venv-assistant/bin/python ]]; then
    echo 'Assistant runtime is missing. Follow docs/SCIENTIFIC_ASSISTANT_SETUP.md to install it.' >&2
    exit 1
  fi
  echo 'Starting website with private assistant configuration. Keys stay on the server.'
  exec uv run --python .venv-assistant/bin/python --no-project --env-file .env.assistant \
    python -m fireatlas.web "${website_args[@]}" "$@"
fi
echo 'No .env.assistant found: starting with stored-data tools; conversational AI is unavailable.'
exec uv run python -m fireatlas.web "${website_args[@]}" "$@"
