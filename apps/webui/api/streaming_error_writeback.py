"""Session writeback helpers for WebUI streaming errors."""

from __future__ import annotations

import contextlib
import time
from typing import Callable


def provider_details_label(error_type: str) -> str | None:
    if error_type == 'cancelled':
        return 'Cancellation details'
    if error_type == 'interrupted':
        return 'Interruption details'
    return None


def format_streaming_error_content(
    label: str,
    message: str,
    *,
    hint: str = '',
    always_include_hint: bool = False,
) -> str:
    content = f'**{label}:** {message}'
    if hint or always_include_hint:
        content += f'\n\n*{hint}*'
    return content


def persist_streaming_error_message(
    session,
    *,
    label: str,
    message: str,
    error_type: str,
    hint: str = '',
    details=None,
    always_include_hint: bool = False,
    timestamp_fn: Callable[[], float] = time.time,
    materialize_pending_user_turn: Callable[[object], object] | None = None,
    logger=None,
) -> dict:
    """Persist an assistant error message and clear pending stream state."""
    if materialize_pending_user_turn is not None:
        materialize_pending_user_turn(session)

    session.active_stream_id = None
    session.pending_user_message = None
    session.pending_attachments = []
    session.pending_started_at = None
    if getattr(session, 'messages', None) is None:
        session.messages = []

    error_message = {
        'role': 'assistant',
        'content': format_streaming_error_content(
            label,
            message,
            hint=hint,
            always_include_hint=always_include_hint,
        ),
        'timestamp': int(timestamp_fn()),
        '_error': True,
    }
    if details:
        error_message['provider_details'] = details
    details_label = provider_details_label(error_type)
    if details_label:
        error_message['provider_details_label'] = details_label

    session.messages.append(error_message)
    try:
        session.save()
    except Exception:
        if logger is not None:
            logger.debug("Failed to save streaming error message", exc_info=True)
    return error_message


def emit_and_persist_streaming_error(
    session,
    *,
    label: str,
    message: str,
    error_type: str,
    hint: str = '',
    put,
    provider_error_payload: Callable[[str, str, str], dict],
    finalize_product_turn: Callable[..., object],
    details=None,
    always_include_hint: bool = False,
    materialize_pending_user_turn: Callable[[object], object] | None = None,
    logger=None,
) -> dict:
    """Emit an app error payload and persist the matching assistant error row."""
    error_payload = provider_error_payload(message, error_type, hint)
    finalize_product_turn(
        failed=True,
        error_type=error_type,
        error_message=error_payload.get('message') or label,
    )
    put('apperror', error_payload)
    persist_streaming_error_message(
        session,
        label=label,
        message=error_payload.get('message') or label,
        error_type=error_type,
        hint=hint,
        details=details if details is not None else error_payload.get('details'),
        always_include_hint=always_include_hint,
        materialize_pending_user_turn=materialize_pending_user_turn,
        logger=logger,
    )
    return error_payload


def emit_and_persist_exception_streaming_error(
    session,
    *,
    err_str: str,
    label: str,
    error_type: str,
    hint: str,
    stream_id: str,
    session_id: str,
    ephemeral: bool,
    agent_lock,
    checkpoint_stop,
    checkpoint_thread,
    stop_checkpoint_thread: Callable[[object, object], object],
    stream_writeback_is_current: Callable[[object, str], bool],
    provider_error_payload: Callable[[str, str, str], dict],
    finalize_product_turn: Callable[..., object],
    put,
    append_interrupted_turn_event,
    materialize_pending_user_turn: Callable[[object], object] | None = None,
    persist_error_message_fn=persist_streaming_error_message,
    logger=None,
) -> bool:
    """Emit and persist an exception-path app error.

    Return False when this worker no longer owns the stream writeback.
    """
    error_payload = provider_error_payload(err_str, error_type, hint)
    if session is not None:
        stop_checkpoint_thread(checkpoint_stop, checkpoint_thread)
        lock_ctx = agent_lock if agent_lock is not None else contextlib.nullcontext()
        with lock_ctx:
            if not ephemeral and not stream_writeback_is_current(session, stream_id):
                if logger is not None:
                    logger.info(
                        "Skipping stale stream error writeback for session %s stream %s; active_stream_id=%s",
                        getattr(session, 'session_id', session_id),
                        stream_id,
                        getattr(session, 'active_stream_id', None),
                    )
                return False
            persist_error_message_fn(
                session,
                label=label,
                message=error_payload.get("message") or err_str,
                error_type=error_type,
                hint=hint,
                details=error_payload.get('details'),
                materialize_pending_user_turn=materialize_pending_user_turn,
                logger=logger,
            )
            if not ephemeral:
                append_interrupted_turn_event(
                    session.session_id,
                    stream_id,
                    reason=error_type,
                    logger=logger,
                )
    finalize_product_turn(
        failed=True,
        error_type=error_payload.get('type') or error_type,
        error_message=error_payload.get('message') or err_str or error_type,
    )
    put('apperror', error_payload)
    return True
