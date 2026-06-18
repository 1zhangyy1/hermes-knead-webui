from api.streaming_tool_bridge import StreamingToolEventBridge


class _FakeMeter:
    def __init__(self):
        self.stats_calls = 0

    def get_stats(self):
        self.stats_calls += 1
        return {}


class _Logger:
    def __init__(self):
        self.debugs = []

    def debug(self, *args, **kwargs):
        self.debugs.append((args, kwargs))


def _make_bridge():
    events = []
    reasoning = []
    metering = []
    bumped = []
    live_tool_calls = []
    shared = {"stream1": []}
    checkpoint = [0]
    seen = set()
    fake_meter = _FakeMeter()

    def put(event, data):
        if event == "metering":
            metering.append(data)
        else:
            events.append((event, data))

    bridge = StreamingToolEventBridge(
        stream_id="stream1",
        session_id="session1",
        live_tool_calls=live_tool_calls,
        shared_live_tool_calls=shared,
        checkpoint_activity=checkpoint,
        seen_tool_call_ids=seen,
        put=put,
        emit_reasoning=lambda text: reasoning.append(text),
        usage_snapshot=lambda: {"last_prompt_tokens": 5},
        bump_live_prompt_estimate=lambda messages: bumped.append(messages) or 123,
        tool_result_snippet=lambda result: f"snippet:{result}",
        meter_factory=lambda: fake_meter,
    )
    return bridge, events, reasoning, metering, bumped, live_tool_calls, shared, checkpoint, seen


def test_tool_bridge_emits_started_and_completed_events():
    bridge, events, reasoning, metering, bumped, live_tool_calls, shared, checkpoint, seen = _make_bridge()

    bridge.on_tool("tool.started", "read_file", "reading", {"path": "/tmp/a.py", "extra": "x"})
    bridge.on_tool("tool.completed", "read_file", "done", {"path": "/tmp/a.py"}, duration=1.5, is_error=True)

    assert events[0] == (
        "tool",
        {
            "event_type": "tool.started",
            "name": "read_file",
            "preview": "reading",
            "args": {"path": "/tmp/a.py", "extra": "x"},
        },
    )
    assert events[1] == (
        "tool_complete",
        {
            "event_type": "tool.completed",
            "name": "read_file",
            "preview": "done",
            "args": {"path": "/tmp/a.py"},
            "duration": 1.5,
            "is_error": True,
        },
    )
    assert live_tool_calls == [{"name": "read_file", "args": {"path": "/tmp/a.py", "extra": "x"}, "done": True, "duration": 1.5, "is_error": True}]
    assert shared["stream1"] == [{"name": "read_file", "args": {"path": "/tmp/a.py", "extra": "x"}, "done": True, "duration": 1.5, "is_error": True}]
    assert checkpoint[0] == 1
    assert metering == [
        {"session_id": "session1", "usage": {"last_prompt_tokens": 5}},
        {"session_id": "session1", "usage": {"last_prompt_tokens": 5}},
    ]
    assert reasoning == []
    assert bumped == []
    assert seen == set()


def test_tool_bridge_routes_reasoning_events_without_tool_cards():
    bridge, events, reasoning, metering, bumped, live_tool_calls, shared, checkpoint, seen = _make_bridge()

    bridge.on_tool("reasoning.available", "ignored", "thinking text", {})
    bridge.on_tool("_thinking", "legacy thinking")

    assert reasoning == ["thinking text", "legacy thinking"]
    assert events == []
    assert metering == []
    assert live_tool_calls == []
    assert shared["stream1"] == []
    assert checkpoint[0] == 0


def test_tool_bridge_records_prompt_estimates_from_native_tool_callbacks():
    bridge, events, reasoning, metering, bumped, live_tool_calls, shared, checkpoint, seen = _make_bridge()

    bridge.on_tool_start("call1", "search", {"q": "cats"})
    bridge.on_tool_start("call1", "search", {"q": "duplicate"})
    bridge.on_tool_complete("call1", "search", {}, {"output": "ok"})

    assert seen == {"call1"}
    assert bumped[0] == [{
        "role": "assistant",
        "content": "",
        "tool_calls": [{
            "id": "call1",
            "type": "function",
            "function": {
                "name": "search",
                "arguments": '{"q": "cats"}',
            },
        }],
    }]
    assert bumped[1] == [{
        "role": "tool",
        "name": "search",
        "tool_call_id": "call1",
        "content": "snippet:{'output': 'ok'}",
    }]
    assert metering == [
        {"session_id": "session1", "usage": {"last_prompt_tokens": 5}},
        {"session_id": "session1", "usage": {"last_prompt_tokens": 5}},
        {"session_id": "session1", "usage": {"last_prompt_tokens": 5}},
    ]


def test_tool_bridge_logs_native_prompt_estimate_failures():
    logger = _Logger()
    bridge = StreamingToolEventBridge(
        stream_id="stream1",
        session_id="session1",
        live_tool_calls=[],
        shared_live_tool_calls={"stream1": []},
        checkpoint_activity=[0],
        seen_tool_call_ids=set(),
        put=lambda event, data: None,
        emit_reasoning=lambda text: None,
        usage_snapshot=lambda: {},
        bump_live_prompt_estimate=lambda messages: (_ for _ in ()).throw(RuntimeError("boom")),
        tool_result_snippet=lambda result: str(result),
        logger=logger,
    )

    bridge.on_tool_start("call1", "search", {"q": "cats"})

    assert logger.debugs
