"""Final stream registry cleanup helpers for WebUI streaming workers."""

from __future__ import annotations

from api.config import (
    AGENT_INSTANCES,
    CANCEL_FLAGS,
    STREAMS,
    STREAMS_LOCK,
    STREAM_GOAL_RELATED,
    STREAM_LAST_EVENT_ID,
    STREAM_LIVE_TOOL_CALLS,
    STREAM_PARTIAL_TEXT,
    STREAM_REASONING_TEXT,
    _clear_thread_env,
    unregister_active_run,
    update_active_run,
)
from api.streaming_checkpoint import stop_checkpoint_thread
from api.streaming_runtime_helpers import restore_agent_process_env


def finalize_streaming_run_attempt(
    *,
    run_state,
    gateway_notifications,
    session_id: str,
    profile_env_snapshot,
    runtime_env_snapshot,
    env_lock,
    restore_agent_process_env_fn=restore_agent_process_env,
) -> None:
    """Clean up per-run helpers that are initialised after startup succeeds."""
    if run_state is not None and getattr(run_state, 'metering_ticker', None) is not None:
        run_state.metering_ticker.stop()
    if gateway_notifications is not None:
        gateway_notifications.unregister(session_id)
    restore_agent_process_env_fn(
        profile_env_snapshot,
        runtime_env_snapshot,
        env_lock=env_lock,
    )


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


def finalize_webui_streaming_worker_exit(
    *,
    session,
    stream_id: str,
    agent_lock,
    checkpoint_stop,
    checkpoint_thread,
    last_resort_sync_from_core,
    finalize_product_turn,
    goal_related=STREAM_GOAL_RELATED,
    stop_checkpoint_thread_fn=stop_checkpoint_thread,
    update_active_run_fn=update_active_run,
    clear_thread_env_fn=_clear_thread_env,
    unregister_active_run_fn=unregister_active_run,
) -> None:
    """Finalize a WebUI worker using the standard stream registries."""
    finalize_streaming_worker_exit(
        session=session,
        stream_id=stream_id,
        agent_lock=agent_lock,
        checkpoint_stop=checkpoint_stop,
        checkpoint_thread=checkpoint_thread,
        stop_checkpoint_thread=stop_checkpoint_thread_fn,
        update_active_run=update_active_run_fn,
        last_resort_sync_from_core=last_resort_sync_from_core,
        finalize_product_turn=finalize_product_turn,
        clear_thread_env=clear_thread_env_fn,
        streams=STREAMS,
        cancel_flags=CANCEL_FLAGS,
        agent_instances=AGENT_INSTANCES,
        partial_text=STREAM_PARTIAL_TEXT,
        reasoning_text=STREAM_REASONING_TEXT,
        live_tool_calls=STREAM_LIVE_TOOL_CALLS,
        goal_related=goal_related,
        last_event_ids=STREAM_LAST_EVENT_ID,
        unregister_active_run=unregister_active_run_fn,
        streams_lock=STREAMS_LOCK,
    )
