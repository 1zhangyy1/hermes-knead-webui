"""Session writeback helpers for WebUI streaming errors."""

from __future__ import annotations

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
