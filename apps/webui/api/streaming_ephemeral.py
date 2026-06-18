"""Ephemeral streaming response helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def latest_assistant_answer(messages: list[Any] | None) -> str:
    """Return the last assistant message content from a result message list."""
    for message in reversed(messages or []):
        if isinstance(message, dict) and message.get('role') == 'assistant':
            return str(message.get('content', ''))
    return ''


def emit_ephemeral_done(
    result: dict,
    *,
    session_id: str,
    session_path: str,
    checkpoint_stop=None,
    put,
) -> None:
    """Emit the /btw done event and remove the temporary session file."""
    messages = result.get('messages') or []
    put('done', {
        'session': {'session_id': session_id, 'messages': messages},
        'usage': {'input_tokens': 0, 'output_tokens': 0},
        'ephemeral': True,
        'answer': latest_assistant_answer(messages),
    })
    if checkpoint_stop is not None:
        checkpoint_stop.set()
    try:
        Path(session_path).unlink(missing_ok=True)
    except Exception:
        pass
