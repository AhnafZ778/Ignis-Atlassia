#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
SOURCE="${1:-$(git -C "$REPO_ROOT" remote get-url origin)}"
PORT="${FIREATLAS_SMOKE_PORT:-8799}"
TEMP_ROOT="$(mktemp -d -t fireatlas-smoke.XXXXXX)"
CLONE_DIR="$TEMP_ROOT/repo"
SERVER_PID=""

cleanup() {
  local exit_code=$?
  if [[ -n "$SERVER_PID" ]]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  if [[ "$exit_code" != 0 && -f "$TEMP_ROOT/server.log" ]]; then
    cat "$TEMP_ROOT/server.log" >&2
  fi
  rm -rf "$TEMP_ROOT"
}
trap cleanup EXIT INT TERM

echo "Cloning $SOURCE into a temporary directory"
git clone --quiet --depth 1 "$SOURCE" "$CLONE_DIR"
cd "$CLONE_DIR"

echo "Installing locked core dependencies"
uv sync --frozen

echo "Starting the authentic-data demo on port $PORT"
uv run python -m fireatlas.web \
  --db data/fireatlas.sqlite3 \
  --host 127.0.0.1 \
  --port "$PORT" >"$TEMP_ROOT/server.log" 2>&1 &
SERVER_PID=$!

BASE_URL="http://127.0.0.1:$PORT"
READY=0
for ((attempt = 1; attempt <= 60; attempt++)); do
  if python3 - "$BASE_URL/api/meta" <<'PY' >/dev/null 2>&1
import sys
import urllib.request

with urllib.request.urlopen(sys.argv[1], timeout=2) as response:
    if response.status != 200:
        raise SystemExit(1)
PY
  then
    READY=1
    break
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    break
  fi
  sleep 1
done

if [[ "$READY" != 1 ]]; then
  echo "Server did not return HTTP 200 from /api/meta within 60 seconds" >&2
  exit 1
fi

echo "Checking the homepage, authentic sources, and July 2024 calendar value"
python3 - "$BASE_URL" <<'PY'
import json
import sys
import urllib.request

base = sys.argv[1]
with urllib.request.urlopen(base + "/", timeout=10) as response:
    page = response.read().decode("utf-8")
    assert response.status == 200
    assert "Ignis-Atlassia" in page
    assert 'id="earth-frame-host"' in page
print("PASS homepage: HTTP 200")

with urllib.request.urlopen(base + "/api/meta", timeout=10) as response:
    meta = json.load(response)
    assert response.status == 200
    sources = set(meta["available_sources"])
    assert {"MODIS_SP", "VIIRS_SNPP_SP"}.issubset(sources), sources
print("PASS metadata: standard MODIS and S-NPP records are present")

path = "/api/calendar?year=2024&series=joint&bbox=-122,39.5,-121.3,40.5"
with urllib.request.urlopen(base + path, timeout=20) as response:
    calendar = json.load(response)
    assert response.status == 200
    assert calendar["demo_data"] is False
    july = next(month for month in calendar["monthly"] if month["month"] == "2024-07")
    assert july["export_window_complete"] is True, july
    # Independently recounted from the bundled July CSVs: type 0 or missing
    # occupies 1,665 cell-days. Including excluded types 2/3 would give 1,668.
    assert july["detected_cell_days"] == 1665, july
    provenance = {row["source_id"] for row in calendar["provenance"]}
    assert {"MODIS_SP", "VIIRS_SNPP_SP"}.issubset(provenance), provenance
print("PASS calendar: July 2024 = 1,665 eligible joint detected cell-days (authentic bundled export)")
PY

echo "Smoke test passed."
