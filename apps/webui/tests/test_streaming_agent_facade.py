import types

from api import streaming
from api.streaming_agent_facade import get_ai_agent_from_facade


def test_get_ai_agent_returns_cached_streaming_agent(monkeypatch):
    original = streaming.AIAgent
    cached = object()
    monkeypatch.setattr(streaming, "AIAgent", cached)

    assert get_ai_agent_from_facade() is cached
    monkeypatch.setattr(streaming, "AIAgent", original)


def test_get_ai_agent_retries_import_when_missing(monkeypatch):
    class Agent:
        pass

    fake_run_agent = types.SimpleNamespace(AIAgent=Agent)
    monkeypatch.setattr(streaming, "AIAgent", None)
    monkeypatch.setitem(__import__("sys").modules, "run_agent", fake_run_agent)

    assert get_ai_agent_from_facade() is Agent
    assert streaming.AIAgent is Agent
