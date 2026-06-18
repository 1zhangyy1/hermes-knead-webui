"""Successful-turn completion helpers for WebUI streaming workers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from api.streaming_terminal import emit_completed_turn_done


@dataclass(frozen=True)
class CompletedConversationSuccessResult:
    result: dict[str, Any] | None
    runtime: dict[str, Any] | None
    resolved_api_key: Any
    resolved_provider: str | None
    resolved_base_url: str | None
    agent_kwargs: dict[str, Any] | None
    agent: Any
    self_healed: bool
    should_return: bool = False


def handle_completed_conversation_success(
    writeback_result,
    *,
    current_result,
    runtime,
    resolved_api_key,
    resolved_provider: str | None,
    resolved_base_url: str | None,
    agent_kwargs,
    agent,
    self_healed: bool,
    session,
    original_session_id: str,
    config: dict,
    resolved_model: str | None,
    profile_home: str | None,
    goal_related: bool,
    put,
    pending_goal_continuation,
    redact_session_data: Callable[[dict], dict],
    build_done_usage_payload: Callable[..., dict],
    apply_context_window_to_usage: Callable[..., object],
    drain_pending_steer_leftover: Callable[..., object],
    run_post_turn_goal_hook: Callable[..., object],
    finalize_product_turn: Callable[..., object],
    meter_stats_fn: Callable[[], dict],
    run_background_title_update: Callable[..., object],
    maybe_schedule_title_refresh: Callable[..., object],
    logger,
    emit_completed_turn_done_fn=emit_completed_turn_done,
) -> CompletedConversationSuccessResult:
    """Apply writeback self-heal state and emit terminal success events."""
    result = current_result
    if writeback_result.self_healed:
        runtime = writeback_result.runtime
        resolved_api_key = writeback_result.resolved_api_key
        resolved_provider = writeback_result.resolved_provider
        resolved_base_url = writeback_result.resolved_base_url
        agent_kwargs = writeback_result.agent_kwargs
        agent = writeback_result.agent
        self_healed = True
        if writeback_result.result is not None:
            result = writeback_result.result

    if writeback_result.should_return:
        return CompletedConversationSuccessResult(
            result=result,
            runtime=runtime,
            resolved_api_key=resolved_api_key,
            resolved_provider=resolved_provider,
            resolved_base_url=resolved_base_url,
            agent_kwargs=agent_kwargs,
            agent=agent,
            self_healed=self_healed,
            should_return=True,
        )

    completed_turn_state = writeback_result.completed_turn_state
    emit_completed_turn_done_fn(
        session,
        original_session_id=original_session_id,
        token_usage=completed_turn_state.token_usage,
        turn_metadata=completed_turn_state.turn_metadata,
        config=config,
        resolved_model=resolved_model or '',
        resolved_provider=resolved_provider or '',
        agent=agent,
        profile_home=profile_home,
        goal_related=goal_related,
        put=put,
        pending_goal_continuation=pending_goal_continuation,
        tool_calls=completed_turn_state.tool_calls,
        title_plan=completed_turn_state.title_plan,
        redact_session_data=redact_session_data,
        build_done_usage_payload=build_done_usage_payload,
        apply_context_window_to_usage=apply_context_window_to_usage,
        drain_pending_steer_leftover=drain_pending_steer_leftover,
        run_post_turn_goal_hook=run_post_turn_goal_hook,
        finalize_product_turn=finalize_product_turn,
        meter_stats_fn=meter_stats_fn,
        run_background_title_update=run_background_title_update,
        maybe_schedule_title_refresh=maybe_schedule_title_refresh,
        logger=logger,
    )
    return CompletedConversationSuccessResult(
        result=result,
        runtime=runtime,
        resolved_api_key=resolved_api_key,
        resolved_provider=resolved_provider,
        resolved_base_url=resolved_base_url,
        agent_kwargs=agent_kwargs,
        agent=agent,
        self_healed=self_healed,
    )
