"""Terminal post-done SSE events for completed WebUI streaming turns."""

from __future__ import annotations

import threading
from typing import Callable


def emit_success_post_done_events(
    session,
    *,
    original_session_id: str,
    should_background_title: bool,
    title_user_text: str,
    title_assistant_text: str,
    put: Callable[[str, dict], object],
    agent,
    meter_stats_fn: Callable[[], dict],
    run_background_title_update: Callable[..., object],
    maybe_schedule_title_refresh: Callable[..., object],
    thread_factory=threading.Thread,
) -> str:
    """Emit final metering and stream-close/title-refresh events after ``done``."""
    meter_stats = meter_stats_fn()
    meter_stats['session_id'] = original_session_id
    meter_stats.setdefault('tps_available', False)
    meter_stats.setdefault('estimated', False)
    put('metering', meter_stats)

    if should_background_title and title_user_text and title_assistant_text:
        thread_factory(
            target=run_background_title_update,
            args=(
                session.session_id,
                title_user_text,
                title_assistant_text,
                str(session.title or '').strip(),
                put,
                agent,
            ),
            daemon=True,
        ).start()
        return 'background_title'

    # Use the original session_id parameter, not session.session_id, which may
    # be rotated during context compression while the client still tracks the
    # original stream session id.
    put('stream_end', {'session_id': original_session_id})
    maybe_schedule_title_refresh(session, put, agent)
    return 'stream_end'


def emit_completed_turn_done(
    session,
    *,
    original_session_id: str,
    token_usage,
    turn_metadata,
    config: dict,
    resolved_model: str,
    resolved_provider: str,
    agent,
    profile_home: str | None,
    goal_related: bool,
    put: Callable[[str, dict], object],
    pending_goal_continuation,
    tool_calls: list,
    title_plan,
    redact_session_data: Callable[[dict], dict],
    build_done_usage_payload: Callable[..., dict],
    apply_context_window_to_usage: Callable[..., object],
    drain_pending_steer_leftover: Callable[..., object],
    run_post_turn_goal_hook: Callable[..., object],
    finalize_product_turn: Callable[..., object],
    meter_stats_fn: Callable[[], dict],
    run_background_title_update: Callable[..., object],
    maybe_schedule_title_refresh: Callable[..., object],
    logger=None,
) -> dict:
    """Emit the durable ``done`` payload and terminal events for a completed turn."""
    usage = build_done_usage_payload(
        token_usage,
        duration_seconds=turn_metadata.duration_seconds,
        turn_tps=turn_metadata.turn_tps,
        gateway_routing=turn_metadata.gateway_routing,
    )
    apply_context_window_to_usage(
        usage,
        session,
        agent,
        config,
        resolved_model=resolved_model,
        resolved_provider=resolved_provider,
    )
    drain_pending_steer_leftover(agent, session_id=original_session_id, put=put, logger=logger)
    run_post_turn_goal_hook(
        session,
        session_id=original_session_id,
        profile_home=profile_home,
        goal_related=goal_related,
        put=put,
        pending_goal_continuation=pending_goal_continuation,
        logger=logger,
    )
    finalize_product_turn(failed=False)
    raw_session = session.compact() | {'messages': session.messages, 'tool_calls': tool_calls}
    put('done', {'session': redact_session_data(raw_session), 'usage': usage})
    emit_success_post_done_events(
        session,
        original_session_id=original_session_id,
        should_background_title=title_plan.should_background_title,
        title_user_text=title_plan.user_text,
        title_assistant_text=title_plan.assistant_text,
        put=put,
        agent=agent,
        meter_stats_fn=meter_stats_fn,
        run_background_title_update=run_background_title_update,
        maybe_schedule_title_refresh=maybe_schedule_title_refresh,
    )
    return usage
