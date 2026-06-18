"""Facade wiring from the legacy streaming module into the turn pipeline."""

from __future__ import annotations

from typing import Any

from api.streaming_turn_pipeline import run_streaming_turn_pipeline


def run_streaming_turn_pipeline_from_facade(
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
    finalize_product_turn,
    put_cancel,
    runtime_state: dict[str, Any] | None = None,
    checkpoint_state: dict[str, Any] | None = None,
):
    """Run the turn pipeline using callbacks exposed by ``api.streaming``.

    ``api.streaming`` remains the compatibility surface used by existing tests
    and monkeypatches.  Looking up the callbacks at call time keeps those
    patches visible while moving the dependency wiring out of the main worker.
    """
    from api import streaming as streaming_api

    return run_streaming_turn_pipeline(
        agent_setup=agent_setup,
        session=session,
        session_id=session_id,
        stream_id=stream_id,
        msg_text=msg_text,
        attachments=attachments,
        workspace=workspace,
        product_context=product_context,
        model=model,
        profile_home=profile_home,
        resolved_profile_name=resolved_profile_name,
        run_state=run_state,
        cancel_event=cancel_event,
        agent_lock=agent_lock,
        ephemeral=ephemeral,
        goal_related=goal_related,
        put=put,
        pending_goal_continuation=streaming_api.PENDING_GOAL_CONTINUATION,
        redact_session_data=streaming_api.redact_session_data,
        build_done_usage_payload=streaming_api._build_done_usage_payload,
        apply_context_window_to_usage=streaming_api._apply_context_window_to_usage,
        drain_pending_steer_leftover=streaming_api._drain_pending_steer_leftover,
        run_post_turn_goal_hook=streaming_api._run_post_turn_goal_hook,
        finalize_product_turn=finalize_product_turn,
        meter_stats_fn=streaming_api.meter().get_stats,
        run_background_title_update=streaming_api._run_background_title_update,
        maybe_schedule_title_refresh=streaming_api._maybe_schedule_title_refresh,
        finalize_cancelled_turn=streaming_api._finalize_cancelled_turn,
        put_cancel=put_cancel,
        handle_post_run_cancel=streaming_api._handle_post_run_cancel,
        stop_checkpoint_thread=streaming_api._stop_checkpoint_thread,
        sanitize_messages_for_api=streaming_api._sanitize_messages_for_api,
        stream_writeback_is_current=streaming_api._stream_writeback_is_current,
        classify_provider_error=streaming_api._classify_provider_error,
        provider_error_payload=streaming_api._provider_error_payload,
        append_interrupted_turn_event=streaming_api._append_interrupted_turn_event,
        materialize_pending_user_turn=streaming_api._materialize_pending_user_turn_before_error,
        has_new_assistant_reply=streaming_api._has_new_assistant_reply,
        assistant_reply_added_after_current_turn=streaming_api._assistant_reply_added_after_current_turn,
        preserve_pre_compression_snapshot=streaming_api._preserve_pre_compression_snapshot,
        compression_anchor_message_key=streaming_api._compression_anchor_message_key,
        compact_summary_text=streaming_api._compact_summary_text,
        compression_summary_from_messages=streaming_api._compression_summary_from_messages,
        title_from_fn=streaming_api.title_from,
        is_provisional_title=streaming_api._is_provisional_title,
        looks_invalid_generated_title=streaming_api._looks_invalid_generated_title,
        first_exchange_snippets=streaming_api._first_exchange_snippets,
        extract_gateway_routing_metadata=streaming_api._extract_gateway_routing_metadata,
        custom_provider_resolver=streaming_api.resolve_custom_provider_connection,
        agent_instances=streaming_api.AGENT_INSTANCES,
        streams_lock=streaming_api.STREAMS_LOCK,
        webui_ephemeral_system_prompt=streaming_api._webui_ephemeral_system_prompt,
        logger=streaming_api.logger,
        runtime_state=runtime_state,
        checkpoint_state=checkpoint_state,
    )
