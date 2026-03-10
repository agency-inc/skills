#!/bin/sh
set -eu

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "Error: uv is required. Install it from https://docs.astral.sh/uv/" >&2
  exit 1
fi

cd "$SCRIPTS_DIR"

if [ ! -d .venv ]; then
  uv venv .venv
fi

uv pip install -e "." --quiet
echo "agency-kb installed at: $SCRIPTS_DIR/.venv/bin/agency-kb"
