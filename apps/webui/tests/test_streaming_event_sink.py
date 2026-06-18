import queue
import threading

from api.streaming_event_sink import StreamingEventSink


class _Logger:
    def __init__(self):
        self.debugs = []

    def debug(self, *args, **kwargs):
        self.debugs.append((args, kwargs))


class _Journal:
    def __init__(self, *, event_id="evt_1", fail=False):
        self.event_id = event_id
        self.fail = fail
        self.calls = []

    def append_sse_event(self, event, data):
        self.calls.append((event, data))
        if self.fail:
            raise RuntimeError("journal failed")
        return {"event_id": self.event_id}


def _make_sink(*, cancel_event=None, journal=None):
    q = queue.Queue()
    logger = _Logger()
    last_event_ids = {}
    sink = StreamingEventSink(
        stream_id="stream1",
        queue=q,
        cancel_event=cancel_event or threading.Event(),
        run_journal=journal,
        last_event_ids=last_event_ids,
        logger=logger,
    )
    return sink, q, logger, last_event_ids


def test_event_sink_journals_before_queue_delivery_and_records_event_id():
    journal = _Journal(event_id="event_42")
    sink, q, logger, last_event_ids = _make_sink(journal=journal)

    sink.put("token", {"text": "hello"})

    assert journal.calls == [("token", {"text": "hello"})]
    assert last_event_ids == {"stream1": "event_42"}
    assert q.get_nowait() == ("token", {"text": "hello"})
    assert logger.debugs == []


def test_event_sink_drops_non_terminal_events_after_cancel():
    cancel_event = threading.Event()
    cancel_event.set()
    sink, q, logger, last_event_ids = _make_sink(cancel_event=cancel_event, journal=_Journal())

    sink.put("token", {"text": "late"})
    sink.put("cancel", {"message": "Cancelled"})

    assert q.get_nowait() == ("cancel", {"message": "Cancelled"})
    assert q.empty()
    assert last_event_ids == {"stream1": "evt_1"}


def test_event_sink_still_queues_when_journal_write_fails():
    sink, q, logger, last_event_ids = _make_sink(journal=_Journal(fail=True))

    sink.put("tool", {"name": "read_file"})

    assert q.get_nowait() == ("tool", {"name": "read_file"})
    assert last_event_ids == {}
    assert logger.debugs

