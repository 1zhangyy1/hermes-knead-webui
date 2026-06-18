import builtins
import sys
import types

from api.streaming_gateway_notifications import (
    GatewayNotificationRegistrations,
    register_streaming_gateway_notifications,
)


class Logger:
    def __init__(self):
        self.messages = []

    def debug(self, *args, **kwargs):
        self.messages.append((args, kwargs))


def _module(register_calls, unregister_calls, event_name):
    module = types.ModuleType(f'fake_{event_name}')

    def register(session_id, callback):
        register_calls.append((event_name, session_id, callback))

    def unregister(session_id):
        unregister_calls.append((event_name, session_id))

    module.register_gateway_notify = register
    module.unregister_gateway_notify = unregister
    return module


def test_register_streaming_gateway_notifications_registers_and_forwards(monkeypatch):
    register_calls = []
    unregister_calls = []
    events = []
    monkeypatch.setitem(sys.modules, 'tools', types.ModuleType('tools'))
    monkeypatch.setitem(sys.modules, 'tools.approval', _module(register_calls, unregister_calls, 'approval'))
    monkeypatch.setitem(sys.modules, 'api.clarify', _module(register_calls, unregister_calls, 'clarify'))

    registrations = register_streaming_gateway_notifications(
        'sid-1',
        put=lambda event, data: events.append((event, data)),
    )

    assert registrations.approval_registered is True
    assert registrations.clarify_registered is True
    assert len(register_calls) == 2
    register_calls[0][2]({'command': 'rm'})
    register_calls[1][2]({'question': 'choose'})
    assert events == [
        ('approval', {'command': 'rm'}),
        ('clarify', {'question': 'choose'}),
    ]

    registrations.unregister('sid-1')
    assert unregister_calls == [('approval', 'sid-1'), ('clarify', 'sid-1')]


def test_register_streaming_gateway_notifications_logs_missing_modules(monkeypatch):
    logger = Logger()
    real_import = builtins.__import__

    def raise_gateway_import_error(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {'tools.approval', 'api.clarify'}:
            raise ImportError(name)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, '__import__', raise_gateway_import_error)
    monkeypatch.delitem(sys.modules, 'tools.approval', raising=False)
    monkeypatch.delitem(sys.modules, 'api.clarify', raising=False)

    registrations = register_streaming_gateway_notifications(
        'sid-1',
        put=lambda event, data: None,
        logger=logger,
    )

    assert registrations.approval_registered is False
    assert registrations.clarify_registered is False
    assert logger.messages


def test_gateway_notification_registrations_unregister_logs_failures():
    logger = Logger()

    def fail(_session_id):
        raise RuntimeError('boom')

    registrations = GatewayNotificationRegistrations(
        unregister_approval=fail,
        approval_registered=True,
        unregister_clarify=fail,
        clarify_registered=True,
        logger=logger,
    )

    registrations.unregister('sid-1')

    assert len(logger.messages) == 2
