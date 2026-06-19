from api import streaming
from api import streaming_runtime_facade as facade


def test_clarify_timeout_seconds_uses_streaming_get_config(monkeypatch):
    calls = []

    def fake_clarify_timeout_seconds(get_config_fn, default=120):
        calls.append((get_config_fn, default))
        return 42

    monkeypatch.setattr(facade, "clarify_timeout_seconds", fake_clarify_timeout_seconds)

    assert facade.clarify_timeout_seconds_from_facade(7) == 42
    assert calls == [(streaming.get_config, 7)]
