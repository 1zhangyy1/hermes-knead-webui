"""Runtime callback bridge setup for WebUI streaming workers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from api.config import (
    STREAM_LIVE_TOOL_CALLS,
    STREAM_PARTIAL_TEXT,
    STREAM_REASONING_TEXT,
)
from api.streaming_output_bridge import StreamingOutputBridge
from api.streaming_tool_bridge import StreamingToolEventBridge


@dataclass(frozen=True)
class StreamingBridgeBundle:
    output_bridge: StreamingOutputBridge
    tool_bridge: StreamingToolEventBridge
    live_tool_calls: list
    checkpoint_activity: list


def initialize_webui_streaming_bridges(
    *,
    stream_id: str,
    session_id: str,
    run_state,
    put: Callable[[str, dict], None],
    tool_result_snippet: Callable[[object], str],
    logger=None,
) -> StreamingBridgeBundle:
    """Create the output/tool callback bridges for a streaming turn."""
    live_tool_calls = []
    output_bridge = StreamingOutputBridge(
        stream_id=stream_id,
        session_id=session_id,
        partial_texts=STREAM_PARTIAL_TEXT,
        reasoning_texts=STREAM_REASONING_TEXT,
        usage_snapshot=run_state.live_usage_snapshot,
        put=put,
    )
    # Keep the activity counter mutable so the checkpoint thread sees tool
    # completions without sharing a larger state object.
    checkpoint_activity = [0]
    tool_bridge = StreamingToolEventBridge(
        stream_id=stream_id,
        session_id=session_id,
        live_tool_calls=live_tool_calls,
        shared_live_tool_calls=STREAM_LIVE_TOOL_CALLS,
        checkpoint_activity=checkpoint_activity,
        seen_tool_call_ids=run_state.seen_tool_call_ids,
        put=put,
        emit_reasoning=output_bridge.on_reasoning,
        usage_snapshot=run_state.live_usage_snapshot,
        bump_live_prompt_estimate=run_state.bump_live_prompt_estimate,
        tool_result_snippet=tool_result_snippet,
        logger=logger,
    )
    return StreamingBridgeBundle(
        output_bridge=output_bridge,
        tool_bridge=tool_bridge,
        live_tool_calls=live_tool_calls,
        checkpoint_activity=checkpoint_activity,
    )
