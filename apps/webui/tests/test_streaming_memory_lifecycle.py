import sys
import types

from api.streaming_memory_lifecycle import mark_completed_turn_memory_lifecycle


class Logger:
    def __init__(self):
        self.messages = []

    def debug(self, *args, **kwargs):
        self.messages.append((args, kwargs))


def test_mark_completed_turn_memory_lifecycle_calls_session_lifecycle(monkeypatch):
    calls = []
    module = types.ModuleType('api.session_lifecycle')
    module.mark_turn_completed = lambda session_id, agent=None: calls.append((session_id, agent))
    monkeypatch.setitem(sys.modules, 'api.session_lifecycle', module)
    agent = object()

    assert mark_completed_turn_memory_lifecycle('sid-1', agent) is True
    assert calls == [('sid-1', agent)]


def test_mark_completed_turn_memory_lifecycle_logs_failure(monkeypatch):
    module = types.ModuleType('api.session_lifecycle')

    def boom(*args, **kwargs):
        raise RuntimeError('boom')

    module.mark_turn_completed = boom
    monkeypatch.setitem(sys.modules, 'api.session_lifecycle', module)
    logger = Logger()

    assert mark_completed_turn_memory_lifecycle('sid-1', object(), logger=logger) is False
    assert logger.messages
