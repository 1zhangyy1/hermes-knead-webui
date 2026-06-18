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


def handle_completed_conversation_post_run(
    result: dict,
    *,
    session,
    session_id: str,
    stream_id: str,
    cancel_event,
    agent_lock,
    finalize_cancelled_turn,
    put_cancel,
    ephemeral: bool,
    checkpoint_stop,
    checkpoint_thread,
    put,
    handle_post_run_cancel,
    stop_checkpoint_thread_fn,
    emit_ephemeral_done_fn=emit_ephemeral_done,
    logger=None,
) -> bool:
    """Handle cancel/ephemeral/checkpoint gates after ``run_conversation``."""
    if handle_post_run_cancel(
        cancel_event,
        session,
        stream_id,
        agent_lock,
        finalize_cancelled_turn,
        put_cancel,
        ephemeral=ephemeral,
        checkpoint_stop=checkpoint_stop,
        checkpoint_thread=checkpoint_thread,
        logger=logger,
    ):
        return True
    if ephemeral:
        emit_ephemeral_done_fn(
            result,
            session_id=session_id,
            session_path=session.path,
            checkpoint_stop=checkpoint_stop,
            put=put,
        )
        return True
    stop_checkpoint_thread_fn(checkpoint_stop, checkpoint_thread)
    if handle_post_run_cancel(
        cancel_event,
        session,
        stream_id,
        agent_lock,
        finalize_cancelled_turn,
        put_cancel,
        ephemeral=False,
        logger=logger,
    ):
        return True
    return False
