"""Cancellation persistence helpers for WebUI streaming runs."""

from __future__ import annotations

import pathlib
import time
from typing import Callable

from api.streaming_errors import CANCEL_MARKER_PATTERNS


def session_has_cancel_marker(session, *, marker_patterns=CANCEL_MARKER_PATTERNS) -> bool:
    """Return True if a visible cancel/interrupted marker is already persisted."""
    for msg in reversed(getattr(session, 'messages', None) or []):
        if not isinstance(msg, dict):
            continue
        if msg.get('role') == 'user':
            return False
        if msg.get('role') != 'assistant':
            continue
        content = msg.get('content')
        text = ''
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict):
                    parts.append(str(part.get('text') or part.get('content') or ''))
            text = '\n'.join(parts)
        normalized = text.strip().lower()
        if any(pattern in normalized for pattern in marker_patterns):
            return True
    return False


def cleanup_ephemeral_cancelled_turn(session, *, logger=None) -> None:
    """Remove transient /btw session state after a cancel without saving it."""
    session.active_stream_id = None
    session.pending_user_message = None
    session.pending_attachments = []
    session.pending_started_at = None
    try:
        pathlib.Path(session.path).unlink(missing_ok=True)
    except Exception:
        if logger is not None:
            logger.debug("Failed to clean up ephemeral cancelled session", exc_info=True)


def persist_cancelled_turn(
    session,
    *,
    materialize_pending_user_turn: Callable,
    cancelled_turn_content_fn: Callable[[str], str],
    message: str = 'Task cancelled.',
    session_has_cancel_marker_fn: Callable = session_has_cancel_marker,
    clock: Callable[[], float] = time.time,
) -> None:
    """Persist a user-cancelled terminal state without provider-error wording."""
    materialize_pending_user_turn(session)
    session.active_stream_id = None
    session.pending_user_message = None
    session.pending_attachments = []
    session.pending_started_at = None
    if not session_has_cancel_marker_fn(session):
        session.messages.append({
            'role': 'assistant',
            'content': cancelled_turn_content_fn(message),
            '_error': True,
            'provider_details': str(message or 'Task cancelled.').strip(),
            'provider_details_label': 'Cancellation details',
            'timestamp': int(clock()),
        })


def finalize_cancelled_turn(
    session,
    *,
    persist_cancelled_turn_fn: Callable,
    cleanup_ephemeral_cancelled_turn_fn: Callable = cleanup_ephemeral_cancelled_turn,
    ephemeral: bool = False,
    message: str = 'Task cancelled.',
    logger=None,
) -> None:
    """Finalize a cancelled turn for persistent or ephemeral sessions."""
    if ephemeral:
        cleanup_ephemeral_cancelled_turn_fn(session)
        return
    persist_cancelled_turn_fn(session, message=message)
    try:
        session.save()
    except Exception:
        if logger is not None:
            logger.debug("Failed to persist cancelled turn", exc_info=True)
