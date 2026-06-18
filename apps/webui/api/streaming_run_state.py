"""Startup state helpers for WebUI streaming runs."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable

from api.streaming_agent_status import make_agent_status_callback
from api.streaming_event_sink import StreamingEventSink
from api.streaming_live_usage import LiveUsageTracker
from api.streaming_metering import StreamingMeteringTicker


@dataclass
class StreamingRunState:
    cancel_event: Any
    live_usage_tracker: LiveUsageTracker
    event_sink: StreamingEventSink
    metering_ticker: StreamingMeteringTicker
    agent_status_callback: Callable

    @property
    def seen_tool_call_ids(self):
        return self.live_usage_tracker.seen_tool_call_ids

    def put(self, event, data) -> None:
        self.event_sink.put(event, data)

    def bump_live_prompt_estimate(self, messages) -> int:
        return self.live_usage_tracker.bump_prompt_estimate(messages)

    def live_usage_snapshot(self):
        return self.live_usage_tracker.snapshot()


def initialize_streaming_run_state(
    *,
    stream_id: str,
    session_id: str,
    queue,
    run_journal,
    streams_lock,
    cancel_flags: dict,
    partial_texts: dict,
    reasoning_texts: dict,
    live_tool_calls: dict,
    last_event_ids: dict,
    get_session: Callable[[], object | None],
    get_agent: Callable[[], object | None],
    logger,
    event_factory=threading.Event,
    live_usage_tracker_factory=LiveUsageTracker,
    event_sink_factory=StreamingEventSink,
    metering_ticker_factory=StreamingMeteringTicker,
    status_callback_factory=make_agent_status_callback,
) -> StreamingRunState:
    """Register per-stream state and return the runtime adapters used by the worker."""
    cancel_event = event_factory()
    with streams_lock:
        cancel_flags[stream_id] = cancel_event
        partial_texts[stream_id] = ''
        reasoning_texts[stream_id] = ''
        live_tool_calls[stream_id] = []

    live_usage_tracker = live_usage_tracker_factory(
        get_session=get_session,
        get_agent=get_agent,
    )
    event_sink = event_sink_factory(
        stream_id=stream_id,
        queue=queue,
        cancel_event=cancel_event,
        run_journal=run_journal,
        last_event_ids=last_event_ids,
        logger=logger,
    )
    state = StreamingRunState(
        cancel_event=cancel_event,
        live_usage_tracker=live_usage_tracker,
        event_sink=event_sink,
        metering_ticker=None,
        agent_status_callback=None,
    )
    state.metering_ticker = metering_ticker_factory(
        stream_id=stream_id,
        session_id=session_id,
        usage_snapshot=state.live_usage_snapshot,
        put=state.put,
    ).start()
    state.agent_status_callback = status_callback_factory(
        session_id=session_id,
        put=state.put,
    )
    return state
