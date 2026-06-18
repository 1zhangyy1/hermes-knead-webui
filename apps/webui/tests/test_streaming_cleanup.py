from api.streaming_cleanup import cleanup_stream_registries


class DummyLock:
    def __init__(self):
        self.entered = False
        self.exited = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc, tb):
        self.exited = True


def test_cleanup_stream_registries_removes_all_per_stream_state():
    stream_id = 'stream-1'
    registries = [{stream_id: 'value'} for _ in range(8)]
    unregistered = []
    lock = DummyLock()

    cleanup_stream_registries(
        stream_id,
        streams=registries[0],
        cancel_flags=registries[1],
        agent_instances=registries[2],
        partial_text=registries[3],
        reasoning_text=registries[4],
        live_tool_calls=registries[5],
        goal_related=registries[6],
        last_event_ids=registries[7],
        unregister_active_run=unregistered.append,
        streams_lock=lock,
    )

    assert lock.entered is True
    assert lock.exited is True
    assert all(stream_id not in registry for registry in registries)
    assert unregistered == [stream_id]


def test_cleanup_stream_registries_does_not_require_existing_keys():
    unregistered = []

    cleanup_stream_registries(
        'missing-stream',
        streams={},
        cancel_flags={},
        agent_instances={},
        partial_text={},
        reasoning_text={},
        live_tool_calls={},
        goal_related={},
        last_event_ids={},
        unregister_active_run=unregistered.append,
        streams_lock=DummyLock(),
    )

    assert unregistered == ['missing-stream']
