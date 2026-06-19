from api import streaming
from api import streaming_chat_steer_facade as facade


def test_handle_chat_steer_uses_streaming_runtime_dependencies(monkeypatch):
    calls = []
    handler = object()
    body = {"session_id": "sid-1", "text": "hint"}

    def fake_handle_chat_steer(handler_arg, body_arg, *, get_session, logger=None):
        calls.append((handler_arg, body_arg, get_session, logger))
        return True

    monkeypatch.setattr(facade, "handle_chat_steer", fake_handle_chat_steer)

    assert facade.handle_chat_steer_from_facade(handler, body) is True
    assert calls == [(handler, body, streaming.get_session, streaming.logger)]
