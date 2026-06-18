from api.streaming_tool_bridge import StreamingToolEventBridge


def _make_bridge():
    events = []
    reasoning = []
    metering = []
    bumped = []
    live_tool_calls = []
    shared = {"stream1": []}
    checkpoint = [0]
    seen = set()

    bridge = StreamingToolEventBridge(
        stream_id="stream1",
        session_id="session1",
        live_tool_calls=live_tool_calls,
        shared_live_tool_calls=shared,
        checkpoint_activity=checkpoint,
        seen_tool_call_ids=seen,
        put=lambda event, data: events.append((event, data)),
        emit_reasoning=lambda text: reasoning.append(text),
        emit_metering_snapshot=lambda: metering.append("tick"),
        bump_live_prompt_estimate=lambda messages: bumped.append(messages) or 123,
        tool_result_snippet=lambda result: f"snippet:{result}",
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
    assert metering == ["tick", "tick"]
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
    assert metering == ["tick", "tick", "tick"]
