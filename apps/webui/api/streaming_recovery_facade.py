"""Compatibility facade for WebUI streaming recovery helpers."""

from __future__ import annotations

from api.streaming_recovery import (
    attempt_credential_self_heal,
    last_resort_sync_from_core,
)


def last_resort_sync_from_core_from_facade(session, stream_id, agent_lock) -> None:
    from api import streaming
    from api.models import _apply_core_sync_or_error_marker, _get_profile_home

    return last_resort_sync_from_core(
        session,
        stream_id,
        agent_lock,
        cancel_flags=streaming.CANCEL_FLAGS,
        get_profile_home=_get_profile_home,
        apply_core_sync_or_error_marker=_apply_core_sync_or_error_marker,
        logger=streaming.logger,
    )


def attempt_credential_self_heal_from_facade(provider_id, session_id, agent_lock_ref):
    from api import streaming

    return attempt_credential_self_heal(
        provider_id,
        session_id,
        agent_lock_ref,
        logger=streaming.logger,
    )
