#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${HERMES_WEBUI_VENV:-$ROOT/apps/webui/.venv311}"
PYTHON_BIN="${PYTHON:-python3}"

if [[ ! -d "$ROOT/runtimes/hermes-agent" ]]; then
  echo "Missing vendored Hermes runtime: $ROOT/runtimes/hermes-agent" >&2
  exit 1
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "[setup-local] creating Python virtualenv at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

VENV_PYTHON="$VENV_DIR/bin/python"

echo "[setup-local] installing Python dependencies"
"$VENV_PYTHON" -m pip install --quiet --upgrade pip "setuptools>=77" wheel
"$VENV_PYTHON" -m pip install --quiet -e "$ROOT/runtimes/hermes-agent"
"$VENV_PYTHON" -m pip install --quiet -r "$ROOT/apps/webui/requirements-dev.txt"

if [[ ! -f "$ROOT/.env" && -f "$ROOT/.env.example" ]]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "[setup-local] created .env from .env.example"
fi

mkdir -p "$ROOT/.hermes-home"

echo "[setup-local] ready"
echo "Next: edit .env, then run: pnpm hermes:model"
