from api import streaming
from api import streaming_context_facade as facade


def test_preserve_pre_compression_snapshot_uses_streaming_runtime_dependencies(monkeypatch):
    calls = []

    def fake_preserve(session, old_sid, *, session_dir, logger):
        calls.append((session, old_sid, session_dir, logger))

    monkeypatch.setattr(facade, "preserve_pre_compression_snapshot", fake_preserve)

    session = object()
    facade.preserve_pre_compression_snapshot_from_facade(session, "old-sid")

    assert calls == [(session, "old-sid", streaming.SESSION_DIR, streaming.logger)]


def test_stream_writeback_is_current_matches_active_stream():
    class Session:
        active_stream_id = "current"

    assert facade.stream_writeback_is_current_from_facade(Session(), "current") is True
    assert facade.stream_writeback_is_current_from_facade(Session(), "stale") is False
    assert facade.stream_writeback_is_current_from_facade(Session(), "") is False
