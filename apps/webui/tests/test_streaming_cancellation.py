import threading

from api.streaming_cancellation import register_agent_instance_or_cancel


class _Agent:
    def __init__(self):
        self.interrupts = []

    def interrupt(self, message):
        self.interrupts.append(message)


def test_register_agent_instance_or_cancel_registers_when_not_cancelled():
    lock = threading.Lock()
    agent_instances = {}
    cancel_flags = {"stream-1": threading.Event()}
    finalize_calls = []
    put_cancel_calls = []

    ok = register_agent_instance_or_cancel(
        "stream-1",
        _Agent(),
        session=object(),
        streams_lock=lock,
        agent_instances=agent_instances,
        cancel_flags=cancel_flags,
        agent_lock=threading.Lock(),
        finalize_cancelled_turn_fn=lambda *args, **kwargs: finalize_calls.append((args, kwargs)),
        put_cancel_fn=lambda: put_cancel_calls.append(True),
    )

    assert ok is True
    assert "stream-1" in agent_instances
    assert finalize_calls == []
    assert put_cancel_calls == []


def test_register_agent_instance_or_cancel_interrupts_and_finalizes_when_cancelled():
    lock = threading.Lock()
    agent_lock = threading.Lock()
    agent_instances = {}
    cancel_flag = threading.Event()
    cancel_flag.set()
    cancel_flags = {"stream-1": cancel_flag}
    agent = _Agent()
    session = object()
    finalize_calls = []
    put_cancel_calls = []

    def finalize(session_arg, *, ephemeral=False, message=''):
        finalize_calls.append((session_arg, ephemeral, message))

    ok = register_agent_instance_or_cancel(
        "stream-1",
        agent,
        session=session,
        streams_lock=lock,
        agent_instances=agent_instances,
        cancel_flags=cancel_flags,
        agent_lock=agent_lock,
        finalize_cancelled_turn_fn=finalize,
        put_cancel_fn=lambda: put_cancel_calls.append(True),
        ephemeral=True,
    )

    assert ok is False
    assert agent_instances["stream-1"] is agent
    assert agent.interrupts == ["Cancelled before start"]
    assert finalize_calls == [(session, True, 'Task cancelled before start.')]
    assert put_cancel_calls == [True]
