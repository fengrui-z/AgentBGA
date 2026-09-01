#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}
OUTPUT_DIR=${1:-${AGENTBGA_TOURNAMENT_OUT:-}}

if [[ -z "$OUTPUT_DIR" ]]; then
  echo "usage: $0 OUTPUT_DIR" >&2
  echo "or set AGENTBGA_TOURNAMENT_OUT" >&2
  exit 64
fi

cd "$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

"$PYTHON_BIN" examples/frontier12_tournament.py check

RUN_ARGS=(
  examples/frontier12_tournament.py run
  --out "$OUTPUT_DIR"
  --workers 16
)

if [[ -f "$OUTPUT_DIR/config.json" ]]; then
  RUN_ARGS+=(--resume --retry-errors)
fi

exec "$PYTHON_BIN" "${RUN_ARGS[@]}"
