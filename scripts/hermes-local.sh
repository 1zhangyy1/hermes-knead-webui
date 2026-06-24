#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$ROOT/.env" ]]; then
  _knead_env_filtered="$(mktemp)"
  grep -vE '^[[:space:]]*(export[[:space:]]+)?(UID|GID|EUID|EGID|PPID)=' "$ROOT/.env" > "$_knead_env_filtered" || true
  set -a
  # shellcheck disable=SC1090
  source "$_knead_env_filtered"
  set +a
  rm -f "$_knead_env_filtered"
fi

resolve_repo_path() {
  local value="${1:-}"
  if [[ -z "$value" || "$value" == /* || "$value" == "~"* ]]; then
    printf '%s' "$value"
  else
    printf '%s/%s' "$ROOT" "$value"
  fi
}

VENV_DIR="$(resolve_repo_path "${HERMES_WEBUI_VENV:-apps/webui/.venv311}")"
VENV_PYTHON="$(resolve_repo_path "${HERMES_WEBUI_PYTHON:-$VENV_DIR/bin/python}")"
HERMES_HOME="$(resolve_repo_path "${HERMES_HOME:-.hermes-home}")"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Project Hermes Python not found: $VENV_PYTHON" >&2
  echo "Run pnpm setup:local first." >&2
  exit 1
fi

export HERMES_HOME
export PYTHONPATH="$ROOT/runtimes/hermes-agent${PYTHONPATH:+:$PYTHONPATH}"

exec "$VENV_PYTHON" "$ROOT/runtimes/hermes-agent/hermes" "$@"
