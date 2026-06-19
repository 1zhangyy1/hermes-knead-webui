"""Compatibility facade for title helpers exposed from ``api.streaming``."""

from __future__ import annotations

import threading

from api.streaming_title_refresh import (
    maybe_schedule_title_refresh,
    put_title_status,
    run_background_title_refresh,
    run_background_title_update,
)


def is_provisional_title_from_facade(current_title: str, messages) -> bool:
    from api import streaming as streaming_api

    return streaming_api._is_provisional_title_impl(
        current_title,
        messages,
        title_from_fn=streaming_api.title_from,
    )


def put_title_status_from_facade(
    put_event,
    session_id: str,
    status: str,
    reason: str = '',
    title: str = '',
    raw_preview: str = '',
) -> None:
    from api import streaming as streaming_api

    put_title_status(
        put_event,
        session_id,
        status,
        reason,
        title,
        raw_preview,
        logger=streaming_api.logger,
    )


def run_background_title_update_from_facade(
    session_id: str,
    user_text: str,
    assistant_text: str,
    placeholder_title: str,
    put_event,
    agent=None,
):
    from api import streaming as streaming_api

    return run_background_title_update(
        session_id,
        user_text,
        assistant_text,
        placeholder_title,
        put_event,
        agent,
        get_session=streaming_api.get_session,
        put_title_status_fn=streaming_api._put_title_status,
        looks_invalid_generated_title=streaming_api._looks_invalid_generated_title,
        is_provisional_title=streaming_api._is_provisional_title,
        aux_title_configured=streaming_api._aux_title_configured,
        generate_title_for_agent=streaming_api._generate_llm_session_title_for_agent,
        generate_title_via_aux=streaming_api._generate_llm_session_title_via_aux,
        fallback_title_from_exchange=streaming_api._fallback_title_from_exchange,
        is_generic_fallback_title=streaming_api._is_generic_fallback_title,
        get_session_agent_lock=streaming_api._get_session_agent_lock,
        lock=streaming_api.LOCK,
        sessions=streaming_api.SESSIONS,
        logger=streaming_api.logger,
    )


def run_background_title_refresh_from_facade(
    session_id: str,
    user_text: str,
    assistant_text: str,
    current_title: str,
    put_event,
    agent=None,
):
    from api import streaming as streaming_api

    return run_background_title_refresh(
        session_id,
        user_text,
        assistant_text,
        current_title,
        put_event,
        agent,
        get_session=streaming_api.get_session,
        put_title_status_fn=streaming_api._put_title_status,
        aux_title_configured=streaming_api._aux_title_configured,
        generate_title_for_agent=streaming_api._generate_llm_session_title_for_agent,
        generate_title_via_aux=streaming_api._generate_llm_session_title_via_aux,
        get_session_agent_lock=streaming_api._get_session_agent_lock,
        lock=streaming_api.LOCK,
        sessions=streaming_api.SESSIONS,
        logger=streaming_api.logger,
    )


def maybe_schedule_title_refresh_from_facade(session, put_event, agent):
    from api import streaming as streaming_api

    return maybe_schedule_title_refresh(
        session,
        put_event,
        agent,
        get_title_refresh_interval_fn=streaming_api._get_title_refresh_interval,
        count_exchanges=streaming_api._count_exchanges,
        latest_exchange_snippets=streaming_api._latest_exchange_snippets,
        run_background_title_refresh_fn=streaming_api._run_background_title_refresh,
        thread_factory=threading.Thread,
    )
