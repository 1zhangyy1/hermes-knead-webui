from api.streaming_context import capture_turn_start_snapshot


class _Session:
    def __init__(self):
        self.messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        self.context_messages = [
            {"role": "system", "content": "summary"},
        ]
        self.pending_started_at = 123.0


class _Compressor:
    compression_count = 4


class _Agent:
    context_compressor = _Compressor()


def test_capture_turn_start_snapshot_uses_pending_started_at_and_copies_messages():
    session = _Session()

    snapshot = capture_turn_start_snapshot(
        session,
        _Agent(),
        "next",
        now_fn=lambda: 999.0,
    )

    assert snapshot.started_at == 123.0
    assert snapshot.previous_messages == session.messages
    assert snapshot.previous_messages is not session.messages
    assert snapshot.previous_context_messages == session.context_messages
    assert snapshot.pre_compression_count == 4


def test_capture_turn_start_snapshot_falls_back_to_now_when_marker_missing():
    session = _Session()
    session.pending_started_at = 0

    snapshot = capture_turn_start_snapshot(
        session,
        object(),
        "next",
        now_fn=lambda: 999.0,
    )

    assert snapshot.started_at == 999.0
    assert snapshot.pre_compression_count == 0
