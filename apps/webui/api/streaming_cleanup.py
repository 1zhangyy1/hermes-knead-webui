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
