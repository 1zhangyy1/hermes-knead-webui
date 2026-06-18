from api.streaming_output_bridge import StreamingOutputBridge


class _FakeMeter:
    def __init__(self):
        self.token_calls = []
        self.reasoning_calls = []
        self.stats_calls = 0

    def get_stats(self):
        self.stats_calls += 1
        return {}

    def record_token(self, stream_id, count):
        self.token_calls.append((stream_id, count))

    def record_reasoning(self, stream_id, count):
        self.reasoning_calls.append((stream_id, count))


def _make_bridge(clock_values=None):
    events = []
    fake_meter = _FakeMeter()
    partials = {"stream1": ""}
    reasonings = {"stream1": ""}
    values = iter(clock_values or [1.0, 1.2, 1.4])
    bridge = StreamingOutputBridge(
        stream_id="stream1",
        session_id="session1",
        partial_texts=partials,
        reasoning_texts=reasonings,
        usage_snapshot=lambda: {"last_prompt_tokens": 5},
        put=lambda event, data: events.append((event, data)),
        meter_factory=lambda: fake_meter,
        clock=lambda: next(values),
    )
    return bridge, events, fake_meter, partials, reasonings


def test_output_bridge_records_token_partial_text_and_metering():
    bridge, events, fake_meter, partials, reasonings = _make_bridge()

    assert bridge.token_sent is False
    assert bridge.on_token("hello") is True

    assert bridge.token_sent is True
    assert partials["stream1"] == "hello"
    assert fake_meter.token_calls == [("stream1", 1)]
    assert events == [
        ("token", {"text": "hello"}),
        ("metering", {
            "session_id": "session1",
            "usage": {"last_prompt_tokens": 5},
            "tps_available": False,
            "estimated": False,
        }),
    ]
    assert bridge.on_token(None) is False


def test_output_bridge_records_reasoning_text_and_metering():
    bridge, events, fake_meter, partials, reasonings = _make_bridge()

    emitted = bridge.on_reasoning("thinking")

    assert emitted == "thinking"
    assert bridge.reasoning_text == "thinking"
    assert reasonings["stream1"] == "thinking"
    assert fake_meter.reasoning_calls == [("stream1", 1)]
    assert events[0] == ("reasoning", {"text": "thinking"})
    assert events[1][0] == "metering"
    assert bridge.on_reasoning(None) == ""


def test_output_bridge_throttles_metering_events():
    bridge, events, fake_meter, partials, reasonings = _make_bridge(clock_values=[1.0, 1.2, 1.25])

    assert bridge.emit_metering() is True
    assert events == [("metering", {
        "session_id": "session1",
        "usage": {"last_prompt_tokens": 5},
        "tps_available": False,
        "estimated": False,
    })]

    assert bridge.on_token("x") is True
    assert events[-1] == ("token", {"text": "x"})
    assert len(events) == 2
    assert fake_meter.token_calls == [("stream1", 1)]


def test_output_bridge_emits_interim_assistant_event():
    bridge, events, fake_meter, partials, reasonings = _make_bridge()

    assert bridge.on_interim_assistant("  Inspecting repo  ", already_streamed=True) is True
    assert bridge.on_interim_assistant("   ") is False
    assert bridge.on_interim_assistant(None) is False

    assert events == [
        ("interim_assistant", {"text": "Inspecting repo", "already_streamed": True})
    ]
