#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export NEXT_AI_PROJECT_ROOT="${NEXT_AI_PROJECT_ROOT:-$ROOT}"
export HERMES_WEBUI_HOST="${HERMES_WEBUI_HOST:-127.0.0.1}"
export HERMES_WEBUI_PORT="${HERMES_WEBUI_PORT:-8788}"
export HERMES_HOME="${HERMES_HOME:-$ROOT/.hermes-home}"

if [[ -z "${HERMES_WEBUI_AGENT_DIR:-}" && -f "$ROOT/vendor/hermes-agent/run_agent.py" ]]; then
  export HERMES_WEBUI_AGENT_DIR="$ROOT/vendor/hermes-agent"
fi

cd "$ROOT/apps/webui"
exec "${HERMES_WEBUI_PYTHON:-python3}" bootstrap.py
