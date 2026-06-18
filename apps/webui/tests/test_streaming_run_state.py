import threading

import api.config as cfg
from api.streaming_run_state import (
    StreamingRunState,
    initialize_streaming_run_state,
    initialize_webui_streaming_run_state,
)


class _Tracker:
    def __init__(self, *, get_session, get_agent):
        self.get_session = get_session
        self.get_agent = get_agent
        self.seen_tool_call_ids = {"seen-tool"}

    def bump_prompt_estimate(self, messages):
        return len(messages or [])

    def snapshot(self):
        return {
            "session": self.get_session(),
            "agent": self.get_agent(),
        }


class _Sink:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.events = []

    def put(self, event, data):
        self.events.append((event, data))


class _Ticker:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True
        return self

    def stop(self):
        self.stopped = True


def test_initialize_streaming_run_state_registers_stream_and_adapters():
    cancel_flags = {}
    partial_texts = {}
    reasoning_texts = {}
    live_tool_calls = {}
    last_event_ids = {}
    status_calls = []
    session = object()
    agent = object()

    def status_callback_factory(**kwargs):
        status_calls.append(kwargs)
        return "status-callback"

    state = initialize_streaming_run_state(
        stream_id="stream-1",
        session_id="sid-1",
        queue=object(),
        run_journal="journal",
        streams_lock=threading.Lock(),
        cancel_flags=cancel_flags,
        partial_texts=partial_texts,
        reasoning_texts=reasoning_texts,
        live_tool_calls=live_tool_calls,
        last_event_ids=last_event_ids,
        get_session=lambda: session,
        get_agent=lambda: agent,
        logger=object(),
        live_usage_tracker_factory=_Tracker,
        event_sink_factory=_Sink,
        metering_ticker_factory=_Ticker,
        status_callback_factory=status_callback_factory,
    )

    assert isinstance(state, StreamingRunState)
    assert cancel_flags["stream-1"] is state.cancel_event
    assert partial_texts["stream-1"] == ""
    assert reasoning_texts["stream-1"] == ""
    assert live_tool_calls["stream-1"] == []
    assert state.seen_tool_call_ids == {"seen-tool"}
    assert state.bump_live_prompt_estimate(["a", "b"]) == 2
    assert state.live_usage_snapshot() == {"session": session, "agent": agent}
    assert state.metering_ticker.started is True
    assert state.agent_status_callback == "status-callback"

    state.put("delta", {"text": "hi"})
    assert state.event_sink.events == [("delta", {"text": "hi"})]

    ticker_kwargs = state.metering_ticker.kwargs
    assert ticker_kwargs["stream_id"] == "stream-1"
    assert ticker_kwargs["session_id"] == "sid-1"
    assert ticker_kwargs["usage_snapshot"]() == {"session": session, "agent": agent}
    ticker_kwargs["put"]("metering", {"ok": True})
    assert state.event_sink.events[-1] == ("metering", {"ok": True})

    assert len(status_calls) == 1
    assert status_calls[0]["session_id"] == "sid-1"
    status_calls[0]["put"]("status", {"phase": "running"})
    assert state.event_sink.events[-1] == ("status", {"phase": "running"})


def test_initialize_webui_streaming_run_state_uses_standard_registries():
    stream_id = "stream-webui-run-state"
    session = object()
    agent = object()

    with cfg.STREAMS_LOCK:
        cfg.CANCEL_FLAGS.pop(stream_id, None)
        cfg.STREAM_PARTIAL_TEXT.pop(stream_id, None)
        cfg.STREAM_REASONING_TEXT.pop(stream_id, None)
        cfg.STREAM_LIVE_TOOL_CALLS.pop(stream_id, None)
        cfg.STREAM_LAST_EVENT_ID.pop(stream_id, None)

    try:
        state = initialize_webui_streaming_run_state(
            stream_id=stream_id,
            session_id="sid-webui-run-state",
            queue=object(),
            run_journal="journal",
            get_session=lambda: session,
            get_agent=lambda: agent,
            logger=object(),
            live_usage_tracker_factory=_Tracker,
            event_sink_factory=_Sink,
            metering_ticker_factory=_Ticker,
            status_callback_factory=lambda **_kwargs: "status-callback",
        )

        with cfg.STREAMS_LOCK:
            assert cfg.CANCEL_FLAGS[stream_id] is state.cancel_event
            assert cfg.STREAM_PARTIAL_TEXT[stream_id] == ""
            assert cfg.STREAM_REASONING_TEXT[stream_id] == ""
            assert cfg.STREAM_LIVE_TOOL_CALLS[stream_id] == []
        assert state.live_usage_snapshot() == {"session": session, "agent": agent}
        assert state.event_sink.kwargs["last_event_ids"] is cfg.STREAM_LAST_EVENT_ID
    finally:
        with cfg.STREAMS_LOCK:
            cfg.CANCEL_FLAGS.pop(stream_id, None)
            cfg.STREAM_PARTIAL_TEXT.pop(stream_id, None)
            cfg.STREAM_REASONING_TEXT.pop(stream_id, None)
            cfg.STREAM_LIVE_TOOL_CALLS.pop(stream_id, None)
            cfg.STREAM_LAST_EVENT_ID.pop(stream_id, None)
