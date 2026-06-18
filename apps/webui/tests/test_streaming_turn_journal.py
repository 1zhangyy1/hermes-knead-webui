from api import streaming_turn_journal as subject


def test_latest_assistant_message_index_returns_last_assistant():
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "one"},
        {"role": "tool", "content": "ignored"},
        {"role": "assistant", "content": "two"},
    ]

    assert subject.latest_assistant_message_index(messages) == 3
    assert subject.latest_assistant_message_index([{"role": "user"}]) is None
    assert subject.latest_assistant_message_index(None) is None


def test_append_assistant_started_turn_event_uses_last_assistant_timestamp(monkeypatch):
    events = []

    monkeypatch.setattr(
        subject,
        "append_turn_journal_event_for_stream",
        lambda session_id, stream_id, event: events.append((session_id, stream_id, event)),
    )

    subject.append_assistant_started_turn_event(
        "sid",
        "stream",
        [
            {"role": "assistant", "timestamp": 10},
            {"role": "user", "timestamp": 11},
            {"role": "assistant", "timestamp": 12},
        ],
        clock=lambda: 99,
    )

    assert events == [(
        "sid",
        "stream",
        {
            "event": "assistant_started",
            "created_at": 12.0,
            "assistant_message_index": 2,
        },
    )]


def test_append_completed_turn_event_includes_latest_assistant_index(monkeypatch):
    events = []

    monkeypatch.setattr(
        subject,
        "append_turn_journal_event_for_stream",
        lambda session_id, stream_id, event: events.append((session_id, stream_id, event)),
    )

    subject.append_completed_turn_event(
        "sid",
        "stream",
        [{"role": "user"}, {"role": "assistant"}],
        clock=lambda: 42,
    )

    assert events == [(
        "sid",
        "stream",
        {
            "event": "completed",
            "created_at": 42,
            "assistant_message_index": 1,
        },
    )]
