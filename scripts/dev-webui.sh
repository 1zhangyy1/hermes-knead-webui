#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export NEXT_AI_PROJECT_ROOT="${NEXT_AI_PROJECT_ROOT:-$ROOT}"
export HERMES_WEBUI_HOST="${HERMES_WEBUI_HOST:-127.0.0.1}"
export HERMES_WEBUI_PORT="${HERMES_WEBUI_PORT:-8788}"
export HERMES_HOME="${HERMES_HOME:-$ROOT/.hermes-home}"
export HERMES_WEBUI_STATE_DIR="${HERMES_WEBUI_STATE_DIR:-$HERMES_HOME/webui}"

if [[ -z "${HERMES_WEBUI_AGENT_DIR:-}" && -f "$ROOT/runtimes/hermes-agent/run_agent.py" ]]; then
  export HERMES_WEBUI_AGENT_DIR="$ROOT/runtimes/hermes-agent"
fi

if [[ -z "${HERMES_WEBUI_PYTHON:-}" && -x "$ROOT/apps/webui/.venv311/bin/python" ]]; then
  export HERMES_WEBUI_PYTHON="$ROOT/apps/webui/.venv311/bin/python"
fi

cd "$ROOT/apps/webui"
exec "${HERMES_WEBUI_PYTHON:-python3}" bootstrap.py
