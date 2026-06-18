"""Completed-turn pipeline orchestration for WebUI streaming workers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from api.streaming_completed_writeback import handle_completed_conversation_writeback
from api.streaming_conversation_run import run_agent_conversation_and_handle_post_run
from api.streaming_success_completion import handle_completed_conversation_success
from api.streaming_turn_start import prepare_streaming_turn_input


@dataclass(frozen=True)
class StreamingTurnPipelineResult:
    should_return: bool = False
    result: dict[str, Any] | None = None
    runtime: dict[str, Any] | None = None
    resolved_api_key: Any = None
    resolved_provider: str | None = None
    resolved_base_url: str | None = None
    agent_kwargs: dict[str, Any] | None = None
    agent: Any = None
    self_healed: bool = False
    checkpoint_stop: Any = None
    checkpoint_thread: Any = None


def run_streaming_turn_pipeline(
    *,
    agent_setup,
    session,
    session_id: str,
    stream_id: str,
    msg_text: str,
    attachments,
    workspace,
    product_context,
    model,
    profile_home,
    resolved_profile_name,
    run_state,
    cancel_event,
    agent_lock,
    ephemeral: bool,
    goal_related: bool,
    put,
    pending_goal_continuation,
    redact_session_data: Callable[[dict], dict],
    build_done_usage_payload,
    apply_context_window_to_usage,
    drain_pending_steer_leftover,
    run_post_turn_goal_hook,
    finalize_product_turn,
    meter_stats_fn,
    run_background_title_update,
    maybe_schedule_title_refresh,
    finalize_cancelled_turn,
    put_cancel,
    handle_post_run_cancel,
    stop_checkpoint_thread,
    sanitize_messages_for_api,
    stream_writeback_is_current,
    classify_provider_error,
    provider_error_payload,
    append_interrupted_turn_event,
    materialize_pending_user_turn,
    has_new_assistant_reply,
    assistant_reply_added_after_current_turn,
    preserve_pre_compression_snapshot,
    compression_anchor_message_key,
    compact_summary_text,
    compression_summary_from_messages,
    title_from_fn,
    is_provisional_title,
    looks_invalid_generated_title,
    first_exchange_snippets,
    extract_gateway_routing_metadata,
    custom_provider_resolver,
    agent_instances,
    streams_lock,
    webui_ephemeral_system_prompt,
    logger,
    runtime_state: dict[str, Any] | None = None,
    checkpoint_state: dict[str, Any] | None = None,
    prepare_streaming_turn_input_fn=prepare_streaming_turn_input,
    run_agent_conversation_and_handle_post_run_fn=run_agent_conversation_and_handle_post_run,
    handle_completed_conversation_writeback_fn=handle_completed_conversation_writeback,
    handle_completed_conversation_success_fn=handle_completed_conversation_success,
) -> StreamingTurnPipelineResult:
    """Run one prepared streaming turn through input, agent, writeback, and done."""

    def remember(**values) -> None:
        if runtime_state is not None:
            runtime_state.update(values)

    agent = agent_setup.agent
    agent_sig = agent_setup.agent_sig
    agent_factory = agent_setup.agent_factory
    agent_kwargs = agent_setup.agent_kwargs
    agent_params = agent_setup.agent_params
    config = agent_setup.config
    runtime = agent_setup.runtime
    resolved_api_key = agent_setup.resolved_api_key
    resolved_model = agent_setup.resolved_model
    resolved_provider = agent_setup.resolved_provider
    resolved_base_url = agent_setup.resolved_base_url
    output_bridge = agent_setup.output_bridge
    live_tool_calls = agent_setup.live_tool_calls
    checkpoint_activity = agent_setup.checkpoint_activity
    self_healed = False
    result = None
    checkpoint_stop = None
    checkpoint_thread = None

    turn_input = prepare_streaming_turn_input_fn(
        session=session,
        agent=agent,
        msg_text=msg_text,
        attachments=attachments,
        workspace=workspace,
        config=config,
        product_context=product_context,
        agent_lock=agent_lock,
        checkpoint_activity=checkpoint_activity,
        session_id=session_id,
        personality_name=getattr(session, 'personality', None),
        webui_ephemeral_system_prompt=webui_ephemeral_system_prompt,
        logger=logger,
    )
    workspace_system_msg = turn_input.system_message
    user_message = turn_input.user_message
    turn_start = turn_input.turn_start
    previous_messages = turn_start.previous_messages
    previous_context_messages = turn_start.previous_context_messages
    pre_compression_count = turn_start.pre_compression_count
    checkpoint_runner = turn_input.checkpoint_runner
    checkpoint_stop = checkpoint_runner.stop_event
    checkpoint_thread = checkpoint_runner.thread
    if checkpoint_state is not None:
        checkpoint_state['stop'] = checkpoint_stop
        checkpoint_state['thread'] = checkpoint_thread
    remember(
        workspace_system_msg=workspace_system_msg,
        user_message=user_message,
        _previous_messages=previous_messages,
        _previous_context_messages=previous_context_messages,
        _output_bridge=output_bridge,
        _cfg=config,
        _agent_kwargs=agent_kwargs,
        _agent_params=agent_params,
        _agent_sig=agent_sig,
        _AIAgent=agent_factory,
        msg_text=msg_text,
    )

    conversation_run = run_agent_conversation_and_handle_post_run_fn(
        agent=agent,
        user_message=user_message,
        system_message=workspace_system_msg,
        previous_context_messages=previous_context_messages,
        config=config,
        session=session,
        session_id=session_id,
        stream_id=stream_id,
        cancel_event=cancel_event,
        agent_lock=agent_lock,
        finalize_cancelled_turn=finalize_cancelled_turn,
        put_cancel=put_cancel,
        ephemeral=ephemeral,
        checkpoint_stop=checkpoint_stop,
        checkpoint_thread=checkpoint_thread,
        put=put,
        msg_text=msg_text,
        sanitize_messages_for_api=sanitize_messages_for_api,
        handle_post_run_cancel=handle_post_run_cancel,
        stop_checkpoint_thread=stop_checkpoint_thread,
        logger=logger,
    )
    result = conversation_run.result
    if conversation_run.should_return:
        return StreamingTurnPipelineResult(
            should_return=True,
            result=result,
            runtime=runtime,
            resolved_api_key=resolved_api_key,
            resolved_provider=resolved_provider,
            resolved_base_url=resolved_base_url,
            agent_kwargs=agent_kwargs,
            agent=agent,
            self_healed=self_healed,
            checkpoint_stop=checkpoint_stop,
            checkpoint_thread=checkpoint_thread,
        )

    writeback_result = handle_completed_conversation_writeback_fn(
        result,
        session=session,
        agent=agent,
        self_healed=self_healed,
        stream_id=stream_id,
        session_id=session_id,
        cancel_event=cancel_event,
        agent_lock=agent_lock,
        ephemeral=ephemeral,
        previous_messages=previous_messages,
        previous_context_messages=previous_context_messages,
        msg_text=msg_text,
        output_bridge=output_bridge,
        live_tool_calls=live_tool_calls,
        turn_started_at=turn_start.started_at,
        attachments=attachments,
        model=model,
        resolved_model=resolved_model,
        resolved_provider=resolved_provider,
        resolved_base_url=resolved_base_url,
        resolved_profile_name=resolved_profile_name,
        config=config,
        pre_compression_count=pre_compression_count,
        usage_snapshot=run_state.live_usage_snapshot,
        agent_factory=agent_factory,
        agent_kwargs=agent_kwargs,
        agent_params=agent_params,
        agent_sig=agent_sig,
        user_message=user_message,
        system_message=workspace_system_msg,
        custom_provider_resolver=custom_provider_resolver,
        agent_instances=agent_instances,
        streams_lock=streams_lock,
        put=put,
        finalize_cancelled_turn=finalize_cancelled_turn,
        append_interrupted_turn_event=append_interrupted_turn_event,
        put_cancel=put_cancel,
        stream_writeback_is_current=stream_writeback_is_current,
        classify_provider_error=classify_provider_error,
        provider_error_payload=provider_error_payload,
        finalize_product_turn=finalize_product_turn,
        materialize_pending_user_turn=materialize_pending_user_turn,
        sanitize_messages_for_api=sanitize_messages_for_api,
        has_new_assistant_reply=has_new_assistant_reply,
        assistant_reply_added_after_current_turn=assistant_reply_added_after_current_turn,
        preserve_pre_compression_snapshot=preserve_pre_compression_snapshot,
        compression_anchor_message_key=compression_anchor_message_key,
        compact_summary_text=compact_summary_text,
        compression_summary_from_messages=compression_summary_from_messages,
        title_from_fn=title_from_fn,
        is_provisional_title=is_provisional_title,
        looks_invalid_generated_title=looks_invalid_generated_title,
        first_exchange_snippets=first_exchange_snippets,
        extract_gateway_routing_metadata=extract_gateway_routing_metadata,
        logger=logger,
    )
    success_result = handle_completed_conversation_success_fn(
        writeback_result,
        current_result=result,
        runtime=runtime,
        resolved_api_key=resolved_api_key,
        resolved_provider=resolved_provider,
        resolved_base_url=resolved_base_url,
        agent_kwargs=agent_kwargs,
        agent=agent,
        self_healed=self_healed,
        session=session,
        original_session_id=session_id,
        config=config,
        resolved_model=resolved_model,
        profile_home=profile_home,
        goal_related=goal_related,
        put=put,
        pending_goal_continuation=pending_goal_continuation,
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
    result = success_result.result
    runtime = success_result.runtime
    resolved_api_key = success_result.resolved_api_key
    resolved_provider = success_result.resolved_provider
    resolved_base_url = success_result.resolved_base_url
    agent_kwargs = success_result.agent_kwargs
    agent = success_result.agent
    self_healed = success_result.self_healed
    remember(
        _rt=runtime,
        resolved_api_key=resolved_api_key,
        resolved_provider=resolved_provider,
        resolved_base_url=resolved_base_url,
        _agent_kwargs=agent_kwargs,
        agent=agent,
        _self_healed=self_healed,
    )

    return StreamingTurnPipelineResult(
        should_return=success_result.should_return,
        result=result,
        runtime=runtime,
        resolved_api_key=resolved_api_key,
        resolved_provider=resolved_provider,
        resolved_base_url=resolved_base_url,
        agent_kwargs=agent_kwargs,
        agent=agent,
        self_healed=self_healed,
        checkpoint_stop=checkpoint_stop,
        checkpoint_thread=checkpoint_thread,
    )
