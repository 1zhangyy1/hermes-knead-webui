"""SSE event sink for WebUI streaming workers."""

from __future__ import annotations


class StreamingEventSink:
    """Write streaming events to the run journal and live queue."""

    def __init__(self, *, stream_id, queue, cancel_event, run_journal, last_event_ids, logger):
        self.stream_id = stream_id
        self.queue = queue
        self.cancel_event = cancel_event
        self.run_journal = run_journal
        self.last_event_ids = last_event_ids
        self.logger = logger

    def put(self, event, data):
        # If cancelled, drop all further events except the cancel event itself.
        if self.cancel_event.is_set() and event not in ('cancel', 'error'):
            return
        run_journal = self.run_journal
        if run_journal is not None:
            try:
                journaled = run_journal.append_sse_event(event, data)
                # Stage-364: propagate journal event_id via a side-channel dict
                # instead of changing the queue tuple shape. The SSE handler
                # reads this dict at emit time to populate `id:` on live frames.
                event_id = (journaled or {}).get('event_id') if isinstance(journaled, dict) else None
                if event_id:
                    self.last_event_ids[self.stream_id] = event_id
            except Exception:
                self.logger.debug(
                    "Failed to append run journal event %s for stream %s",
                    event,
                    self.stream_id,
                    exc_info=True,
                )
        try:
            q = self.queue
            q.put_nowait((event, data))
        except Exception:
            self.logger.debug("Failed to put event to queue")

