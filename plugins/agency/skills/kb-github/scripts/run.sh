#!/bin/sh
set -eu

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_BIN="$SCRIPTS_DIR/.venv/bin/agency-kb"

if [ ! -f "$VENV_BIN" ]; then
  echo "agency-kb not installed. Running install..." >&2
  "$SCRIPTS_DIR/install.sh"
fi

exec "$VENV_BIN" "$@"
