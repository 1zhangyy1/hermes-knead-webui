from api.streaming_metering import StreamingMeteringTicker


class _FakeStopEvent:
    def __init__(self, waits):
        self.waits = waits
        self.set_called = False

    def wait(self, interval):
        self.waits.append(interval)
        return False

    def set(self):
        self.set_called = True


class _ImmediateThread:
    def __init__(self, *, target, daemon):
        self.target = target
        self.daemon = daemon
        self.started = False

    def start(self):
        self.started = True
        self.target()


class _FakeMeter:
    def __init__(self):
        self.begin_calls = []
        self.intervals = [0.01, 10.0]

    def begin_session(self, stream_id):
        self.begin_calls.append(stream_id)

    def get_interval(self):
        return self.intervals.pop(0)

    def get_stats(self):
        return {"tps_available": False, "estimated": False}


def test_streaming_metering_ticker_begins_session_and_emits_usage():
    fake_meter = _FakeMeter()
    events = []
    waits = []
    stop_event = _FakeStopEvent(waits)

    ticker = StreamingMeteringTicker(
        stream_id="stream1",
        session_id="session1",
        usage_snapshot=lambda: {"last_prompt_tokens": 12},
        put=lambda event, data: events.append((event, data)),
        meter_factory=lambda: fake_meter,
        thread_factory=_ImmediateThread,
        event_factory=lambda: stop_event,
    ).start()

    assert ticker.thread.started is True
    assert fake_meter.begin_calls == ["stream1"]
    assert waits == [0.01]
    assert events == [
        (
            "metering",
            {
                "tps_available": False,
                "estimated": False,
                "session_id": "session1",
                "usage": {"last_prompt_tokens": 12},
            },
        )
    ]

    ticker.stop()
    assert stop_event.set_called is True

