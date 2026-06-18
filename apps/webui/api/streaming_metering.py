"""Background metering ticker for WebUI streaming."""

from __future__ import annotations

import threading
from typing import Callable

from api.metering import meter


class StreamingMeteringTicker:
    """Emit periodic live metering SSE events while a stream is active."""

    def __init__(
        self,
        *,
        stream_id: str,
        session_id: str,
        usage_snapshot: Callable[[], dict],
        put: Callable[[str, dict], None],
        meter_factory: Callable = meter,
        thread_factory=threading.Thread,
        event_factory=threading.Event,
    ):
        self.stream_id = stream_id
        self.session_id = session_id
        self.usage_snapshot = usage_snapshot
        self.put = put
        self.meter_factory = meter_factory
        self.thread_factory = thread_factory
        self.stop_event = event_factory()
        self.thread = None

    def start(self):
        self.meter_factory().begin_session(self.stream_id)
        self.thread = self.thread_factory(target=self._run, daemon=True)
        self.thread.start()
        return self

    def stop(self) -> None:
        self.stop_event.set()

    def _run(self) -> None:
        while True:
            interval = self.meter_factory().get_interval()
            if interval >= 10.0:
                break
            if self.stop_event.wait(interval):
                break
            stats = self.meter_factory().get_stats()
            stats['session_id'] = self.session_id
            stats['usage'] = self.usage_snapshot()
            self.put('metering', stats)

