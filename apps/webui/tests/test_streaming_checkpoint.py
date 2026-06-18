from api.streaming_checkpoint import StreamingCheckpointRunner, stop_checkpoint_thread


class RecordingLock:
    def __init__(self):
        self.held = False
        self.enter_count = 0

    def __enter__(self):
        self.enter_count += 1
        self.held = True

    def __exit__(self, exc_type, exc, tb):
        self.held = False


class RecordingSession:
    def __init__(self, lock):
        self.lock = lock
        self.saves = []

    def save(self, **kwargs):
        assert self.lock.held
        self.saves.append(kwargs)


def test_checkpoint_saves_once_per_activity_increment_under_agent_lock():
    lock = RecordingLock()
    activity = [0]
    session = RecordingSession(lock)
    runner = StreamingCheckpointRunner(
        session,
        agent_lock=lock,
        checkpoint_activity=activity,
        thread_factory=lambda **_kwargs: None,
    )

    assert runner.save_if_activity_advanced() is False

    activity[0] = 1
    assert runner.save_if_activity_advanced() is True
    assert runner.save_if_activity_advanced() is False

    activity[0] = 2
    assert runner.save_if_activity_advanced() is True

    assert session.saves == [{"skip_index": True}, {"skip_index": True}]
    assert lock.enter_count == 2


def test_stop_checkpoint_thread_sets_event_and_joins_thread():
    class StopEvent:
        def __init__(self):
            self.set_calls = 0

        def set(self):
            self.set_calls += 1

    class Thread:
        def __init__(self):
            self.join_calls = []

        def join(self, timeout=None):
            self.join_calls.append(timeout)

    stop = StopEvent()
    thread = Thread()

    stop_checkpoint_thread(stop, thread, timeout=3)

    assert stop.set_calls == 1
    assert thread.join_calls == [3]


def test_stop_checkpoint_thread_allows_missing_runner_parts():
    stop_checkpoint_thread(None, None)
