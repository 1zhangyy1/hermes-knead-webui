"""Small runtime helpers for the streaming engine."""

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


WEBUI_VISIBLE_PROGRESS_PROMPT = """
WebUI progress contract:
- For multi-step work that uses tools, provide brief user-visible progress updates as normal assistant content before continuing with tool calls.
- Each update should say what you are about to check, what you just confirmed, or why the next tool call is needed.
- Keep updates concise, factual, and in the user's language. One or two short sentences are enough.
- Do not reveal hidden reasoning, chain-of-thought, private scratchpads, secrets, raw logs, or long tool output.
- For direct answers or very short tasks, skip progress updates and answer normally.
""".strip()


@dataclass(frozen=True)
class StreamingProfileRuntime:
    profile_home: str
    profile_runtime_env: dict
    resolved_profile_name: str | None
    patch_skill_home_modules: Callable | None


@dataclass(frozen=True)
class StreamingProcessEnvSnapshot:
    profile_env_snapshot: dict
    runtime_env_snapshot: dict


def build_agent_thread_env(profile_runtime_env: dict | None, workspace: str, session_id: str, profile_home: str) -> dict:
    """Build thread-local agent env with per-run values overriding profile defaults."""
    env = dict(profile_runtime_env or {})
    env.update({
        'TERMINAL_CWD': str(workspace),
        'HERMES_EXEC_ASK': '1',
        'HERMES_SESSION_KEY': session_id,
        'HERMES_SESSION_ID': session_id,
        'HERMES_SESSION_PLATFORM': 'webui',
        'HERMES_HOME': profile_home,
    })
    return env


def resolve_streaming_profile_runtime(session, *, environ=os.environ) -> StreamingProfileRuntime:
    """Resolve the per-session Hermes profile runtime for a streaming turn."""
    try:
        from api.profiles import (
            patch_skill_home_modules,
            get_hermes_home_for_profile,
            get_profile_runtime_env,
        )
        _profile_home_path = get_hermes_home_for_profile(getattr(session, 'profile', None))
        _profile_home = str(_profile_home_path)
        _profile_runtime_env = get_profile_runtime_env(_profile_home_path)
    except ImportError:
        _profile_home = environ.get('HERMES_HOME', '')
        _profile_runtime_env = {}
        patch_skill_home_modules = None

    # Capture the resolved profile name now, while session context is reliable.
    # Streaming runs in a background thread, so request-local profile state from
    # the HTTP handler thread is not safe to consult later during compression.
    _resolved_profile_name = getattr(session, 'profile', None)
    if not _resolved_profile_name:
        try:
            from api.profiles import get_active_profile_name

            _resolved_profile_name = get_active_profile_name()
        except Exception:
            _resolved_profile_name = None

    return StreamingProfileRuntime(
        profile_home=_profile_home,
        profile_runtime_env=_profile_runtime_env,
        resolved_profile_name=_resolved_profile_name,
        patch_skill_home_modules=patch_skill_home_modules,
    )


def apply_streaming_profile_process_env(
    *,
    profile_runtime_env: dict | None,
    workspace: str,
    session_id: str,
    profile_home: str,
    patch_skill_home_modules: Callable | None,
    env_lock,
) -> StreamingProcessEnvSnapshot:
    """Apply process-level fallback env for tools that bypass thread-local env."""
    runtime_keys = (
        'TERMINAL_CWD',
        'HERMES_EXEC_ASK',
        'HERMES_SESSION_KEY',
        'HERMES_SESSION_ID',
        'HERMES_SESSION_PLATFORM',
        'HERMES_HOME',
    )
    profile_runtime_env = dict(profile_runtime_env or {})
    with env_lock:
        profile_env_snapshot = {key: os.environ.get(key) for key in profile_runtime_env}
        runtime_env_snapshot = {key: os.environ.get(key) for key in runtime_keys}
        os.environ.update(profile_runtime_env)
        os.environ['TERMINAL_CWD'] = str(workspace)
        os.environ['HERMES_EXEC_ASK'] = '1'
        os.environ['HERMES_SESSION_KEY'] = session_id
        os.environ['HERMES_SESSION_ID'] = session_id
        os.environ['HERMES_SESSION_PLATFORM'] = 'webui'
        if profile_home:
            os.environ['HERMES_HOME'] = profile_home
            # Patch module-level caches to match the active profile. Modules
            # are prewarmed before this helper is called, so this remains a
            # lightweight sys.modules lookup path under the env lock (#2024).
            if patch_skill_home_modules is not None:
                patch_skill_home_modules(Path(profile_home))

    return StreamingProcessEnvSnapshot(
        profile_env_snapshot=profile_env_snapshot,
        runtime_env_snapshot=runtime_env_snapshot,
    )


def restore_env_snapshot(snapshot: dict | None) -> None:
    """Restore os.environ values captured as ``key -> old_value``."""
    for key, old_value in (snapshot or {}).items():
        if old_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old_value


def restore_agent_process_env(
    profile_env_snapshot: dict | None,
    runtime_env_snapshot: dict | None,
    *,
    env_lock,
) -> None:
    """Restore process-level env values mutated for a streaming agent run."""
    with env_lock:
        restore_env_snapshot(profile_env_snapshot)
        restore_env_snapshot(runtime_env_snapshot)


def discover_mcp_tools_for_profile() -> bool:
    """Best-effort MCP discovery after the streaming profile env is active."""
    try:
        from tools.mcp_tool import discover_mcp_tools

        discover_mcp_tools()
        return True
    except Exception:
        return False


def clarify_timeout_seconds(get_config_fn, default: int = 120) -> int:
    """Resolve clarify timeout from config, with bounded fallback."""
    try:
        cfg = get_config_fn()
        raw = cfg.get("clarify", {}).get("timeout", default)
        timeout_seconds = int(raw)
        if timeout_seconds <= 0:
            return default
        return timeout_seconds
    except Exception:
        return default


def webui_ephemeral_system_prompt(personality_prompt: Optional[str], product_prompt: Optional[str] = None) -> str:
    """Build WebUI-only runtime instructions that are not persisted to history."""
    parts = []
    if personality_prompt:
        parts.append(str(personality_prompt).strip())
    parts.append(WEBUI_VISIBLE_PROGRESS_PROMPT)
    if product_prompt:
        parts.append(str(product_prompt).strip())
    return "\n\n".join(part for part in parts if part)


def has_new_assistant_reply(all_messages: list, prev_count: int) -> bool:
    """Return True if new messages beyond ``prev_count`` contain assistant text."""
    if len(all_messages) > prev_count:
        candidates = all_messages[prev_count:]
    elif len(all_messages) < prev_count:
        return False
    else:
        return False
    return any(
        m.get('role') == 'assistant' and str(m.get('content') or '').strip()
        for m in candidates
    )


def aiagent_import_error_detail() -> str:
    """Return a multi-line diagnostic string for the "AIAgent not available" path."""
    lines = ["AIAgent not available -- check that hermes-agent is on sys.path"]
    lines.append("")
    lines.append(f"  python:  {sys.executable}")
    agent_dir = os.environ.get("HERMES_WEBUI_AGENT_DIR")
    if agent_dir:
        lines.append(f"  HERMES_WEBUI_AGENT_DIR: {agent_dir}")
    else:
        lines.append("  HERMES_WEBUI_AGENT_DIR: (not set)")

    relevant = [p for p in sys.path if "hermes" in p.lower() or "agent" in p.lower()]
    if relevant:
        lines.append("  sys.path entries mentioning hermes/agent:")
        for entry in relevant[:6]:
            lines.append(f"    - {entry}")
        if len(relevant) > 6:
            lines.append(f"    ... and {len(relevant) - 6} more")
    else:
        lines.append("  sys.path: (no entries mention hermes or agent)")

    lines.append("")
    lines.append("  Most common fix: install the agent in editable mode so its modules")
    lines.append("  appear on sys.path:")
    lines.append("")
    lines.append("    cd /path/to/hermes-agent")
    lines.append("    pip install -e .")
    lines.append("")
    lines.append("  Then restart the WebUI.")
    lines.append("")
    lines.append('  Full troubleshooting: docs/troubleshooting.md ("AIAgent not available")')
    return "\n".join(lines)


def webui_clarify_callback(question, choices, sid, cancel_evt, timeout_fn):
    """Bridge Hermes clarify prompts to the WebUI pending-clarify queue."""
    timeout = timeout_fn()
    choices_list = [str(choice) for choice in (choices or [])]
    data = {
        'question': str(question or ''),
        'choices_offered': choices_list,
        'session_id': sid,
        'kind': 'clarify',
        'requested_at': time.time(),
        'timeout_seconds': timeout,
    }
    try:
        from api.clarify import submit_pending as _submit_clarify_pending, clear_pending as _clear_clarify_pending
    except ImportError:
        return (
            "The user did not provide a response within the time limit. "
            "Use your best judgement to make the choice and proceed."
        )

    entry = _submit_clarify_pending(sid, data)
    deadline = time.monotonic() + timeout
    while True:
        if cancel_evt.is_set():
            _clear_clarify_pending(sid)
            return (
                "The user did not provide a response within the time limit. "
                "Use your best judgement to make the choice and proceed."
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _clear_clarify_pending(sid)
            return (
                "The user did not provide a response within the time limit. "
                "Use your best judgement to make the choice and proceed."
            )
        if entry.event.wait(timeout=min(1.0, remaining)):
            response = str(entry.result or "").strip()
            return (
                response
                or "The user did not provide a response within the time limit. "
                   "Use your best judgement to make the choice and proceed."
            )
