from api import streaming
from api import streaming_cancel_facade as facade


def test_cancel_stream_from_facade_uses_streaming_runtime_dependencies(monkeypatch):
    calls = []

    def fake_cancel_stream_request(stream_id, **kwargs):
        calls.append((stream_id, kwargs))
        return True

    monkeypatch.setattr(facade, "cancel_stream_request", fake_cancel_stream_request)

    assert facade.cancel_stream_from_facade("stream-1") is True
    assert len(calls) == 1
    stream_id, kwargs = calls[0]
    assert stream_id == "stream-1"
    assert kwargs["streams"] is streaming.STREAMS
    assert kwargs["cancel_flags"] is streaming.CANCEL_FLAGS
    assert kwargs["agent_instances"] is streaming.AGENT_INSTANCES
    assert kwargs["partial_texts"] is streaming.STREAM_PARTIAL_TEXT
    assert kwargs["reasoning_texts"] is streaming.STREAM_REASONING_TEXT
    assert kwargs["live_tool_calls"] is streaming.STREAM_LIVE_TOOL_CALLS
    assert kwargs["streams_lock"] is streaming.STREAMS_LOCK
    assert kwargs["get_session"] is streaming.get_session
    assert kwargs["get_session_agent_lock"] is streaming._get_session_agent_lock
    assert kwargs["stream_writeback_is_current"] is streaming._stream_writeback_is_current
    assert kwargs["cancelled_turn_content_fn"] is streaming._cancelled_turn_content
    assert kwargs["logger"] is streaming.logger
