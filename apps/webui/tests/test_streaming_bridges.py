from types import SimpleNamespace

import api.config as cfg
from api.streaming_bridges import (
    StreamingBridgeBundle,
    initialize_webui_streaming_bridges,
)


class _RunState:
    def __init__(self):
        self.seen_tool_call_ids = {"seen"}
        self.prompt_estimates = []

    def live_usage_snapshot(self):
        return {"tokens": 3}

    def bump_live_prompt_estimate(self, messages):
        self.prompt_estimates.append(messages)
        return len(messages or [])


def test_initialize_webui_streaming_bridges_uses_standard_runtime_state():
    events = []
    run_state = _RunState()

    bundle = initialize_webui_streaming_bridges(
        stream_id="stream-bridge",
        session_id="sid-bridge",
        run_state=run_state,
        put=lambda event, data: events.append((event, data)),
        tool_result_snippet=lambda result: str(result),
        logger=SimpleNamespace(debug=lambda *_args, **_kwargs: None),
    )

    assert isinstance(bundle, StreamingBridgeBundle)
    assert bundle.output_bridge.partial_texts is cfg.STREAM_PARTIAL_TEXT
    assert bundle.output_bridge.reasoning_texts is cfg.STREAM_REASONING_TEXT
    assert bundle.tool_bridge.shared_live_tool_calls is cfg.STREAM_LIVE_TOOL_CALLS
    assert bundle.tool_bridge.live_tool_calls is bundle.live_tool_calls
    assert bundle.tool_bridge.checkpoint_activity is bundle.checkpoint_activity
    assert bundle.tool_bridge.seen_tool_call_ids is run_state.seen_tool_call_ids
    assert bundle.tool_bridge.emit_reasoning.__self__ is bundle.output_bridge
    assert bundle.tool_bridge.emit_reasoning.__func__ is bundle.output_bridge.on_reasoning.__func__
    assert bundle.checkpoint_activity == [0]
