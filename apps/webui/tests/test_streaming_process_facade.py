from api import streaming
from api import streaming_process_facade as facade


def test_drain_process_notifications_uses_streaming_logger(monkeypatch):
    calls = []

    def fake_drain(session_id, *, logger=None):
        calls.append((session_id, logger))
        return ["done"]

    monkeypatch.setattr(facade, "drain_webui_process_notifications", fake_drain)

    assert facade.drain_webui_process_notifications_from_facade("session-1") == ["done"]
    assert calls == [("session-1", streaming.logger)]


def test_mark_process_completion_consumed_uses_streaming_logger(monkeypatch):
    calls = []
    registry = object()

    def fake_mark(process_registry, process_id, *, logger=None):
        calls.append((process_registry, process_id, logger))

    monkeypatch.setattr(facade, "mark_process_completion_consumed", fake_mark)

    facade.mark_process_completion_consumed_from_facade(registry, "proc-1")
    assert calls == [(registry, "proc-1", streaming.logger)]
