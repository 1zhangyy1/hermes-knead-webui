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

if [[ -n "${HERMES_HOME:-}" ]]; then
  HERMES_HOME="$(resolve_repo_path "$HERMES_HOME")"
fi
if [[ -n "${HERMES_WEBUI_STATE_DIR:-}" ]]; then
  HERMES_WEBUI_STATE_DIR="$(resolve_repo_path "$HERMES_WEBUI_STATE_DIR")"
fi

# KNEAD_* are the public project env names. NEXT_AI_* is accepted only as a
# compatibility fallback for older local setups.
if [[ -z "${KNEAD_PROJECT_ROOT:-}" && -n "${NEXT_AI_PROJECT_ROOT:-}" ]]; then
  KNEAD_PROJECT_ROOT="$NEXT_AI_PROJECT_ROOT"
fi
if [[ -z "${KNEAD_BUILTIN_PRODUCTS_DIR:-}" && -n "${NEXT_AI_BUILTIN_PRODUCTS_DIR:-}" ]]; then
  KNEAD_BUILTIN_PRODUCTS_DIR="$NEXT_AI_BUILTIN_PRODUCTS_DIR"
fi
if [[ -z "${KNEAD_PRODUCTS_DIR:-}" && -n "${NEXT_AI_PRODUCTS_DIR:-}" ]]; then
  KNEAD_PRODUCTS_DIR="$NEXT_AI_PRODUCTS_DIR"
fi
for _knead_path_var in \
  KNEAD_PROJECT_ROOT NEXT_AI_PROJECT_ROOT \
  KNEAD_BUILTIN_PRODUCTS_DIR NEXT_AI_BUILTIN_PRODUCTS_DIR \
  KNEAD_PRODUCTS_DIR NEXT_AI_PRODUCTS_DIR
do
  _knead_path_value="${!_knead_path_var:-}"
  if [[ -n "$_knead_path_value" ]]; then
    printf -v "$_knead_path_var" '%s' "$(resolve_repo_path "$_knead_path_value")"
  fi
done

export HERMES_WEBUI_HOST="${HERMES_WEBUI_HOST:-127.0.0.1}"
export HERMES_WEBUI_PORT="${HERMES_WEBUI_PORT:-8788}"
export HERMES_HOME="${HERMES_HOME:-$ROOT/.hermes-home}"
export HERMES_WEBUI_STATE_DIR="${HERMES_WEBUI_STATE_DIR:-$HERMES_HOME/webui}"
export KNEAD_PROJECT_ROOT="${KNEAD_PROJECT_ROOT:-${NEXT_AI_PROJECT_ROOT:-$ROOT}}"
export NEXT_AI_PROJECT_ROOT="${NEXT_AI_PROJECT_ROOT:-$KNEAD_PROJECT_ROOT}"
export KNEAD_BUILTIN_PRODUCTS_DIR="${KNEAD_BUILTIN_PRODUCTS_DIR:-${NEXT_AI_BUILTIN_PRODUCTS_DIR:-$KNEAD_PROJECT_ROOT/products}}"
export NEXT_AI_BUILTIN_PRODUCTS_DIR="${NEXT_AI_BUILTIN_PRODUCTS_DIR:-$KNEAD_BUILTIN_PRODUCTS_DIR}"
export KNEAD_PRODUCTS_DIR="${KNEAD_PRODUCTS_DIR:-${NEXT_AI_PRODUCTS_DIR:-$HERMES_WEBUI_STATE_DIR/products}}"
export NEXT_AI_PRODUCTS_DIR="${NEXT_AI_PRODUCTS_DIR:-$KNEAD_PRODUCTS_DIR}"

if [[ -z "${HERMES_WEBUI_AGENT_DIR:-}" && -f "$ROOT/runtimes/hermes-agent/run_agent.py" ]]; then
  export HERMES_WEBUI_AGENT_DIR="$ROOT/runtimes/hermes-agent"
fi

if [[ -z "${HERMES_WEBUI_PYTHON:-}" && -x "$ROOT/apps/webui/.venv311/bin/python" ]]; then
  export HERMES_WEBUI_PYTHON="$ROOT/apps/webui/.venv311/bin/python"
fi

# Ensure the agent can discover the repo-tracked skills (.agents/skills: knead-product,
# impeccable). config.yaml lives in the machine-local HERMES_HOME, so wire it here,
# idempotently, for every checkout.
"${HERMES_WEBUI_PYTHON:-python3}" - "$HERMES_HOME" "$ROOT" <<'PY'
import sys
from pathlib import Path

home, root = Path(sys.argv[1]), Path(sys.argv[2])
cfg = home / "config.yaml"
skills_dir = str(root / ".agents" / "skills")
text = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
if skills_dir not in text:
    if "skills:" not in text:
        text = text.rstrip("\n") + "\nskills:\n  external_dirs:\n"
    elif "external_dirs:" not in text:
        text = text.replace("skills:", "skills:\n  external_dirs:", 1)
    text = text.replace("external_dirs:", f"external_dirs:\n    - {skills_dir}", 1)
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(text, encoding="utf-8")
    print(f"[dev-webui] wired skills.external_dirs -> {skills_dir}")
PY

cd "$ROOT/apps/webui"
exec "${HERMES_WEBUI_PYTHON:-python3}" bootstrap.py
