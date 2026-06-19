"""Compatibility facade for WebUI stream cancellation wiring."""

from __future__ import annotations

from api.streaming_cancellation import cancel_stream_request


def cancel_stream_from_facade(stream_id: str) -> bool:
    from api import config as live_config
    from api import streaming

    return cancel_stream_request(
        stream_id,
        live_config=live_config,
        streams=streaming.STREAMS,
        cancel_flags=streaming.CANCEL_FLAGS,
        agent_instances=streaming.AGENT_INSTANCES,
        partial_texts=streaming.STREAM_PARTIAL_TEXT,
        reasoning_texts=streaming.STREAM_REASONING_TEXT,
        live_tool_calls=streaming.STREAM_LIVE_TOOL_CALLS,
        streams_lock=streaming.STREAMS_LOCK,
        get_session=streaming.get_session,
        get_session_agent_lock=streaming._get_session_agent_lock,
        stream_writeback_is_current=streaming._stream_writeback_is_current,
        cancelled_turn_content_fn=streaming._cancelled_turn_content,
        logger=streaming.logger,
    )
