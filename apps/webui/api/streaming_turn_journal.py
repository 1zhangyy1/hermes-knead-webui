"""Turn-journal lifecycle helpers for WebUI streaming workers."""

from __future__ import annotations

import time
from typing import Callable

from api.turn_journal import append_turn_journal_event_for_stream


def latest_assistant_message_index(messages) -> int | None:
    """Return the newest assistant message index, if one exists."""
    for idx in range(len(messages or []) - 1, -1, -1):
        msg = messages[idx]
        if isinstance(msg, dict) and msg.get('role') == 'assistant':
            return idx
    return None


def append_worker_started_turn_event(
    session_id: str,
    stream_id: str,
    *,
    logger=None,
    clock: Callable[[], float] = time.time,
) -> None:
    append_stream_turn_event_safely(
        session_id,
        stream_id,
        {
            "event": "worker_started",
            "created_at": clock(),
        },
        logger=logger,
        log_label="worker_started",
    )


def append_interrupted_turn_event(
    session_id: str,
    stream_id: str,
    *,
    reason: str = "cancelled",
    logger=None,
    clock: Callable[[], float] = time.time,
) -> None:
    append_stream_turn_event_safely(
        session_id,
        stream_id,
        {
            "event": "interrupted",
            "created_at": clock(),
            "reason": reason,
        },
        logger=logger,
        log_label="interrupted",
    )


def append_assistant_started_turn_event(
    session_id: str,
    stream_id: str,
    messages,
    *,
    logger=None,
    clock: Callable[[], float] = time.time,
) -> None:
    assistant_idx = latest_assistant_message_index(messages)
    if assistant_idx is None:
        return
    assistant = messages[assistant_idx]
    append_stream_turn_event_safely(
        session_id,
        stream_id,
        {
            "event": "assistant_started",
            "created_at": float(assistant.get('timestamp') or clock()),
            "assistant_message_index": assistant_idx,
        },
        logger=logger,
        log_label="assistant_started",
    )


def append_completed_turn_event(
    session_id: str,
    stream_id: str,
    messages,
    *,
    logger=None,
    clock: Callable[[], float] = time.time,
) -> None:
    append_stream_turn_event_safely(
        session_id,
        stream_id,
        {
            "event": "completed",
            "created_at": clock(),
            "assistant_message_index": latest_assistant_message_index(messages),
        },
        logger=logger,
        log_label="completed",
    )


def append_stream_turn_event_safely(
    session_id: str,
    stream_id: str,
    event: dict,
    *,
    logger=None,
    log_label: str | None = None,
) -> None:
    """Append a turn-journal event without letting journal failures stop streaming."""
    try:
        append_turn_journal_event_for_stream(session_id, stream_id, event)
    except Exception:
        if logger is not None:
            logger.debug(
                "Failed to append %s turn journal event",
                log_label or event.get("event") or "stream",
                exc_info=True,
            )
