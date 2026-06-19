"""Compatibility facade for error and cancellation helpers in ``api.streaming``."""

from __future__ import annotations

from api.streaming_cancellation import (
    cleanup_ephemeral_cancelled_turn,
    finalize_cancelled_turn,
    persist_cancelled_turn,
)
from api.streaming_errors import (
    cancelled_turn_content,
    cancelled_turn_hint,
    classify_provider_error,
    preferred_agent_display_name,
    provider_error_payload,
)


def preferred_agent_display_name_from_facade() -> str:
    from api import streaming as streaming_api

    return preferred_agent_display_name(
        load_settings_fn=streaming_api.load_settings,
        logger=streaming_api.logger,
    )


def cancelled_turn_hint_from_facade(agent_name: str | None = None) -> str:
    from api import streaming as streaming_api

    return cancelled_turn_hint(
        agent_name,
        load_settings_fn=streaming_api.load_settings,
        logger=streaming_api.logger,
    )


def classify_provider_error_from_facade(
    err_str: str,
    exc=None,
    *,
    silent_failure: bool = False,
) -> dict:
    from api import streaming as streaming_api

    return classify_provider_error(
        err_str,
        exc,
        silent_failure=silent_failure,
        cancelled_turn_hint_fn=streaming_api._cancelled_turn_hint,
        is_quota_error_text_fn=streaming_api._is_quota_error_text,
    )


def provider_error_payload_from_facade(message: str, err_type: str, hint: str = '') -> dict:
    from api import streaming as streaming_api

    return provider_error_payload(
        message,
        err_type,
        hint,
        redact_text_fn=streaming_api._redact_text,
    )


def cancelled_turn_content_from_facade(message: str = 'Task cancelled.') -> str:
    from api import streaming as streaming_api

    return cancelled_turn_content(
        message,
        cancelled_turn_hint_fn=streaming_api._cancelled_turn_hint,
    )


def persist_cancelled_turn_from_facade(session, *, message: str = 'Task cancelled.') -> None:
    from api import streaming as streaming_api

    persist_cancelled_turn(
        session,
        message=message,
        materialize_pending_user_turn=streaming_api._materialize_pending_user_turn_before_error,
        session_has_cancel_marker_fn=streaming_api._session_has_cancel_marker,
        cancelled_turn_content_fn=streaming_api._cancelled_turn_content,
    )


def cleanup_ephemeral_cancelled_turn_from_facade(session) -> None:
    from api import streaming as streaming_api

    cleanup_ephemeral_cancelled_turn(session, logger=streaming_api.logger)


def finalize_cancelled_turn_from_facade(
    session,
    *,
    ephemeral: bool = False,
    message: str = 'Task cancelled.',
) -> None:
    from api import streaming as streaming_api

    finalize_cancelled_turn(
        session,
        ephemeral=ephemeral,
        message=message,
        cleanup_ephemeral_cancelled_turn_fn=streaming_api._cleanup_ephemeral_cancelled_turn,
        persist_cancelled_turn_fn=streaming_api._persist_cancelled_turn,
        logger=streaming_api.logger,
    )
