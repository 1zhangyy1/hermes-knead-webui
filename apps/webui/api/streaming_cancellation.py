"""Cancellation persistence helpers for WebUI streaming runs."""

from __future__ import annotations

import pathlib
import re
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


def recover_pending_user_turn_on_cancel(session, *, clock: Callable[[], float] = time.time, logger=None, session_id=None) -> bool:
    """Persist pending_user_message into messages when cancel wins the merge race."""
    try:
        pending_user = getattr(session, 'pending_user_message', None)
        pending_atts_raw = getattr(session, 'pending_attachments', None)
        pending_atts = list(pending_atts_raw) if isinstance(pending_atts_raw, (list, tuple)) else []
        pending_started = getattr(session, 'pending_started_at', None) or 0
        messages = session.messages if isinstance(getattr(session, 'messages', None), list) else None
        if not pending_user or messages is None:
            return False

        last_user = None
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get('role') == 'user':
                last_user = msg
                break
        already_persisted = False
        if last_user is not None:
            last_content = last_user.get('content')
            last_ts = last_user.get('timestamp') or 0
            if isinstance(last_content, str) and last_ts >= pending_started:
                if pending_user == last_content or pending_user in last_content:
                    already_persisted = True
        if already_persisted:
            return False

        user_turn: dict = {
            'role': 'user',
            'content': pending_user,
            'timestamp': int(clock()),
        }
        if pending_atts:
            user_turn['attachments'] = pending_atts
        messages.append(user_turn)
        return True
    except Exception:
        if logger is not None:
            logger.debug(
                "Failed to recover pending user message on cancel for %s",
                session_id or getattr(session, 'session_id', '?'),
            )
        return False


def strip_cancel_partial_text(partial_text) -> str:
    """Remove thinking markup from partial streamed text before cancel persistence."""
    text = str(partial_text or '').strip()
    if not text:
        return ''
    stripped = re.sub(
        r'<think(?:ing)?\b[^>]*>.*?</think(?:ing)?>',
        '',
        text,
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()
    return re.sub(
        r'<think(?:ing)?\b[^>]*>.*',
        '',
        stripped,
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()


def append_cancel_partial_and_marker(
    session,
    *,
    partial_text,
    reasoning_text,
    tool_calls,
    cancelled_turn_content_fn: Callable[[str], str],
    session_has_cancel_marker_fn: Callable = session_has_cancel_marker,
    marker_patterns=CANCEL_MARKER_PATTERNS,
    clock: Callable[[], float] = time.time,
) -> None:
    """Append preserved partial output and a cancel marker for a cancelled turn."""
    stripped = strip_cancel_partial_text(partial_text)
    has_reasoning = bool(reasoning_text and str(reasoning_text).strip())
    has_tools = bool(tool_calls)
    cancel_marker_exists = session_has_cancel_marker_fn(session)
    cancel_marker_idx = len(session.messages)
    if cancel_marker_exists:
        for idx in range(len(session.messages) - 1, -1, -1):
            msg = session.messages[idx]
            if not isinstance(msg, dict) or msg.get('role') != 'assistant':
                continue
            content = str(msg.get('content') or '').strip().lower()
            if any(pattern in content for pattern in marker_patterns):
                cancel_marker_idx = idx
                break

    partial_already_present = False
    if stripped:
        for msg in session.messages:
            if not isinstance(msg, dict) or not msg.get('_partial'):
                continue
            if str(msg.get('content') or '').strip() == stripped:
                partial_already_present = True
                break

    if (stripped or has_reasoning or has_tools) and not partial_already_present:
        partial_msg: dict = {
            'role': 'assistant',
            'content': stripped,
            '_partial': True,
            'timestamp': int(clock()),
        }
        if has_reasoning:
            partial_msg['reasoning'] = str(reasoning_text).strip()
        if has_tools:
            partial_msg['_partial_tool_calls'] = list(tool_calls)
        session.messages.insert(cancel_marker_idx, partial_msg)

    if not cancel_marker_exists:
        session.messages.append({
            'role': 'assistant',
            'content': cancelled_turn_content_fn('Task cancelled.'),
            '_error': True,
            'provider_details': 'Task cancelled.',
            'provider_details_label': 'Cancellation details',
            'timestamp': int(clock()),
        })


def persist_cancel_stream_writeback(
    session,
    *,
    partial_text,
    reasoning_text,
    tool_calls,
    cancelled_turn_content_fn: Callable[[str], str],
    logger=None,
    session_id=None,
    clock: Callable[[], float] = time.time,
) -> None:
    """Persist all session-side state for a cancelled streaming turn."""
    if not isinstance(getattr(session, 'messages', None), list):
        session.messages = []
    recover_pending_user_turn_on_cancel(
        session,
        clock=clock,
        logger=logger,
        session_id=session_id,
    )
    session.active_stream_id = None
    session.pending_user_message = None
    session.pending_attachments = []
    session.pending_started_at = None
    append_cancel_partial_and_marker(
        session,
        partial_text=partial_text,
        reasoning_text=reasoning_text,
        tool_calls=tool_calls,
        cancelled_turn_content_fn=cancelled_turn_content_fn,
        clock=clock,
    )
    session.save()


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
