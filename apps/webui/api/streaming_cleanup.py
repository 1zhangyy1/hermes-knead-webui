"""Final stream registry cleanup helpers for WebUI streaming workers."""

from __future__ import annotations


def cleanup_stream_registries(
    stream_id: str,
    *,
    streams,
    cancel_flags,
    agent_instances,
    partial_text,
    reasoning_text,
    live_tool_calls,
    goal_related,
    last_event_ids,
    unregister_active_run,
    streams_lock,
) -> None:
    """Remove per-stream state after a streaming worker exits."""
    with streams_lock:
        streams.pop(stream_id, None)
        cancel_flags.pop(stream_id, None)
        agent_instances.pop(stream_id, None)
        partial_text.pop(stream_id, None)
        reasoning_text.pop(stream_id, None)
        live_tool_calls.pop(stream_id, None)
        goal_related.pop(stream_id, None)
        last_event_ids.pop(stream_id, None)
        unregister_active_run(stream_id)
        # NOTE: do NOT discard PENDING_GOAL_CONTINUATION here. The marker is
        # set by goal_continue inside the same streaming turn and consumed
        # atomically by `_start_chat_stream_for_session` in routes.py.


def finalize_streaming_worker_exit(
    *,
    session,
    stream_id: str,
    agent_lock,
    checkpoint_stop,
    checkpoint_thread,
    stop_checkpoint_thread,
    update_active_run,
    last_resort_sync_from_core,
    finalize_product_turn,
    clear_thread_env,
    streams,
    cancel_flags,
    agent_instances,
    partial_text,
    reasoning_text,
    live_tool_calls,
    goal_related,
    last_event_ids,
    unregister_active_run,
    streams_lock,
    cleanup_stream_registries_fn=cleanup_stream_registries,
) -> None:
    """Run the outer streaming worker finally-block cleanup in order."""
    stop_checkpoint_thread(checkpoint_stop, checkpoint_thread)
    if (
        session is not None
        and getattr(session, 'active_stream_id', None) == stream_id
        and getattr(session, 'pending_user_message', None)
    ):
        update_active_run(stream_id, phase="finalizing")
        last_resort_sync_from_core(session, stream_id, agent_lock)
    finalize_product_turn(failed=True)
    clear_thread_env()
    cleanup_stream_registries_fn(
        stream_id,
        streams=streams,
        cancel_flags=cancel_flags,
        agent_instances=agent_instances,
        partial_text=partial_text,
        reasoning_text=reasoning_text,
        live_tool_calls=live_tool_calls,
        goal_related=goal_related,
        last_event_ids=last_event_ids,
        unregister_active_run=unregister_active_run,
        streams_lock=streams_lock,
    )
