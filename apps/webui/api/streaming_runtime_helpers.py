"""Small runtime helpers for the streaming engine."""

import os
import sys
from typing import Optional


WEBUI_VISIBLE_PROGRESS_PROMPT = """
WebUI progress contract:
- For multi-step work that uses tools, provide brief user-visible progress updates as normal assistant content before continuing with tool calls.
- Each update should say what you are about to check, what you just confirmed, or why the next tool call is needed.
- Keep updates concise, factual, and in the user's language. One or two short sentences are enough.
- Do not reveal hidden reasoning, chain-of-thought, private scratchpads, secrets, raw logs, or long tool output.
- For direct answers or very short tasks, skip progress updates and answer normally.
""".strip()


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
