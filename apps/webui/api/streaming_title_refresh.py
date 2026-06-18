"""Background title update and adaptive refresh orchestration for streaming."""

from __future__ import annotations

import re
import threading
from typing import Callable


def get_title_refresh_interval() -> int:
    """Read the auto_title_refresh_every setting (0 = disabled)."""
    try:
        from api.config import load_settings
        settings = load_settings()
        val = settings.get('auto_title_refresh_every', '0')
        return int(val) if str(val).strip().isdigit() and int(val) > 0 else 0
    except Exception:
        return 0


def put_title_status(
    put_event,
    session_id: str,
    status: str,
    reason: str = '',
    title: str = '',
    raw_preview: str = '',
    *,
    logger=None,
) -> None:
    payload = {'session_id': session_id, 'status': status}
    if reason:
        payload['reason'] = reason
    if title:
        payload['title'] = title
    if raw_preview:
        payload['raw_preview'] = raw_preview
    put_event('title_status', payload)
    if logger is not None:
        logger.info(
            "title_status session=%s status=%s reason=%s title=%r raw_preview=%r",
            session_id,
            status,
            reason or '-',
            title or '',
            (raw_preview or '')[:120],
        )


def run_background_title_update(
    session_id: str,
    user_text: str,
    assistant_text: str,
    placeholder_title: str,
    put_event,
    agent=None,
    *,
    get_session: Callable,
    put_title_status_fn: Callable,
    looks_invalid_generated_title: Callable,
    is_provisional_title: Callable,
    aux_title_configured: Callable,
    generate_title_for_agent: Callable,
    generate_title_via_aux: Callable,
    fallback_title_from_exchange: Callable,
    is_generic_fallback_title: Callable,
    get_session_agent_lock: Callable,
    lock,
    sessions: dict,
    logger=None,
):
    """Generate and publish a better title after `done`, then end the stream."""
    try:
        try:
            s = get_session(session_id)
        except KeyError:
            put_title_status_fn(put_event, session_id, 'skipped', 'missing_session')
            return
        invalid_existing = looks_invalid_generated_title(s.title)
        if getattr(s, 'llm_title_generated', False) and not invalid_existing:
            put_title_status_fn(put_event, session_id, 'skipped', 'already_generated', str(s.title or ''))
            return
        current = str(s.title or '').strip()
        still_auto = (
            current == placeholder_title
            or current in ('Untitled', 'New Chat', '')
            or is_provisional_title(current, s.messages)
            or invalid_existing
        )
        if not still_auto:
            put_title_status_fn(put_event, session_id, 'skipped', 'manual_title', current)
            return
        from api import profiles as profiles_api

        with profiles_api.profile_env_for_background_worker(s, "background title", logger_override=logger):
            aux_configured = aux_title_configured()
            if agent and not aux_configured:
                next_title, llm_status, raw_preview = generate_title_for_agent(agent, user_text, assistant_text)
                if not next_title and llm_status in ('llm_error', 'llm_invalid'):
                    next_title, llm_status, raw_preview = generate_title_via_aux(
                        user_text,
                        assistant_text,
                        agent=agent,
                        use_agent_model=True,
                    )
            else:
                next_title, llm_status, raw_preview = generate_title_via_aux(user_text, assistant_text)
                if not next_title and agent and llm_status in ('llm_error_aux', 'llm_invalid_aux'):
                    next_title, llm_status, raw_preview = generate_title_for_agent(agent, user_text, assistant_text)
            source = llm_status
            if not next_title:
                fallback_title = fallback_title_from_exchange(user_text, assistant_text)
                if fallback_title and not is_generic_fallback_title(fallback_title):
                    if logger is not None:
                        logger.debug("Using local fallback for session title generation")
                    next_title = fallback_title
                    source = 'fallback'
                elif fallback_title and logger is not None:
                    logger.debug("Skipping generic local fallback for session title generation: %r", fallback_title)
        fallback_reason = (
            f'local_summary:{llm_status}'
            if source == 'fallback' and llm_status
            else 'local_summary'
        )
        wrote_title = False
        effective_title = current
        if next_title:
            with get_session_agent_lock(session_id):
                with lock:
                    s = sessions.get(session_id, s)
                    effective_title = str(s.title or '').strip()
                    invalid_existing_now = looks_invalid_generated_title(s.title)
                    still_auto = (
                        effective_title == placeholder_title
                        or effective_title in ('Untitled', 'New Chat', '')
                        or is_provisional_title(effective_title, s.messages)
                        or invalid_existing_now
                    )
                if not still_auto:
                    put_title_status_fn(put_event, session_id, 'skipped', 'manual_title', effective_title)
                    return
                if next_title != effective_title:
                    s.title = next_title
                    s.llm_title_generated = True
                    s.save(touch_updated_at=False)
                    effective_title = s.title
                    wrote_title = True

        if wrote_title:
            if source == 'fallback':
                put_title_status_fn(put_event, session_id, source, fallback_reason, effective_title, raw_preview)
            else:
                put_title_status_fn(put_event, session_id, source, llm_status, effective_title, raw_preview)
            put_event('title', {'session_id': session_id, 'title': effective_title})
        else:
            put_title_status_fn(put_event, session_id, 'skipped', source or 'unchanged', effective_title, raw_preview)
    finally:
        put_event('stream_end', {'session_id': session_id})


def run_background_title_refresh(
    session_id: str,
    user_text: str,
    assistant_text: str,
    current_title: str,
    put_event,
    agent=None,
    *,
    get_session: Callable,
    put_title_status_fn: Callable,
    aux_title_configured: Callable,
    generate_title_for_agent: Callable,
    generate_title_via_aux: Callable,
    get_session_agent_lock: Callable,
    lock,
    sessions: dict,
    logger=None,
):
    """Refresh an existing LLM-generated title using the latest exchange text."""
    try:
        try:
            s = get_session(session_id)
        except KeyError:
            return
        effective = str(s.title or '').strip()
        if effective != current_title:
            put_title_status_fn(put_event, session_id, 'skipped', 'manual_title', effective)
            return
        if not effective or effective in ('Untitled', 'New Chat'):
            return
        from api import profiles as profiles_api

        with profiles_api.profile_env_for_background_worker(s, "background title", logger_override=logger):
            aux_configured = aux_title_configured()
            if agent and not aux_configured:
                next_title, llm_status, raw_preview = generate_title_for_agent(agent, user_text, assistant_text)
                if not next_title and llm_status in ('llm_error', 'llm_invalid'):
                    next_title, llm_status, raw_preview = generate_title_via_aux(
                        user_text,
                        assistant_text,
                        agent=agent,
                        use_agent_model=True,
                    )
            else:
                next_title, llm_status, raw_preview = generate_title_via_aux(user_text, assistant_text)
                if not next_title and agent and llm_status in ('llm_error_aux', 'llm_invalid_aux'):
                    next_title, llm_status, raw_preview = generate_title_for_agent(agent, user_text, assistant_text)
        if not next_title:
            put_title_status_fn(put_event, session_id, 'refresh_skipped', llm_status or 'empty', effective, raw_preview)
            return
        normalized_current = re.sub(r'\s+', ' ', effective).strip().lower()
        normalized_new = re.sub(r'\s+', ' ', next_title).strip().lower()
        if normalized_current == normalized_new:
            put_title_status_fn(put_event, session_id, 'refresh_skipped', 'same_title', effective, raw_preview)
            return
        with get_session_agent_lock(session_id):
            with lock:
                s = sessions.get(session_id, s)
                if str(s.title or '').strip() != current_title:
                    put_title_status_fn(put_event, session_id, 'skipped', 'manual_title', str(s.title or '').strip())
                    return
                s.title = next_title
                s.llm_title_generated = True
                effective_title = s.title
            s.save(touch_updated_at=False)
        put_title_status_fn(put_event, session_id, 'refreshed', llm_status, effective_title, raw_preview)
        put_event('title', {'session_id': session_id, 'title': effective_title})
        if logger is not None:
            logger.info("Adaptive title refresh: session=%s new_title=%r", session_id, effective_title)
    except Exception:
        if logger is not None:
            logger.debug("Background title refresh failed for session %s", session_id, exc_info=True)


def maybe_schedule_title_refresh(
    session,
    put_event,
    agent,
    *,
    get_title_refresh_interval_fn: Callable,
    count_exchanges: Callable,
    latest_exchange_snippets: Callable,
    run_background_title_refresh_fn: Callable,
    thread_factory: Callable = threading.Thread,
) -> None:
    """Check if the session is due for an adaptive title refresh and schedule it."""
    refresh_interval = get_title_refresh_interval_fn()
    if refresh_interval <= 0:
        return
    current_title = str(session.title or '').strip()
    if not current_title or current_title in ('Untitled', 'New Chat'):
        return
    if not getattr(session, 'llm_title_generated', False):
        return
    exchange_count = count_exchanges(session.messages)
    if exchange_count <= 0 or exchange_count % refresh_interval != 0:
        return
    last_u, last_a = latest_exchange_snippets(session.messages)
    if not last_u and not last_a:
        return
    thread_factory(
        target=run_background_title_refresh_fn,
        args=(session.session_id, last_u, last_a, current_title, put_event, agent),
        daemon=True,
    ).start()
