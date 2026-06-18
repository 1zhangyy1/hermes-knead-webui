import threading

from api.streaming_cancellation import handle_post_run_cancel, register_agent_instance_or_cancel


class _Agent:
    def __init__(self):
        self.interrupts = []

    def interrupt(self, message):
        self.interrupts.append(message)


class _Session:
    session_id = "sid-1"


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


def test_handle_post_run_cancel_returns_false_when_not_cancelled():
    cancel_event = threading.Event()

    assert handle_post_run_cancel(
        cancel_event,
        _Session(),
        "stream-1",
        threading.Lock(),
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("finalize")),
        lambda: (_ for _ in ()).throw(AssertionError("put")),
        ephemeral=False,
        append_interrupted_turn_event_fn=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("append")),
    ) is False


def test_handle_post_run_cancel_stops_checkpoint_and_persists_cancelled_turn():
    cancel_event = threading.Event()
    cancel_event.set()
    session = _Session()
    calls = []

    ok = handle_post_run_cancel(
        cancel_event,
        session,
        "stream-1",
        threading.Lock(),
        lambda session_arg, *, ephemeral=False: calls.append(("finalize", session_arg, ephemeral)),
        lambda: calls.append(("put_cancel",)),
        ephemeral=False,
        checkpoint_stop="stop",
        checkpoint_thread="thread",
        stop_checkpoint_thread_fn=lambda stop, thread: calls.append(("stop", stop, thread)),
        append_interrupted_turn_event_fn=lambda session_id, stream_id, logger=None: calls.append(("interrupted", session_id, stream_id)),
    )

    assert ok is True
    assert calls == [
        ("stop", "stop", "thread"),
        ("finalize", session, False),
        ("interrupted", "sid-1", "stream-1"),
        ("put_cancel",),
    ]


def test_handle_post_run_cancel_cleans_ephemeral_session_without_interrupted_event():
    cancel_event = threading.Event()
    cancel_event.set()
    session = _Session()
    calls = []

    ok = handle_post_run_cancel(
        cancel_event,
        session,
        "stream-1",
        threading.Lock(),
        lambda *args, **kwargs: calls.append(("finalize",)),
        lambda: calls.append(("put_cancel",)),
        ephemeral=True,
        cleanup_ephemeral_cancelled_turn_fn=lambda session_arg: calls.append(("cleanup", session_arg)),
        append_interrupted_turn_event_fn=lambda *args, **kwargs: calls.append(("interrupted",)),
    )

    assert ok is True
    assert calls == [("cleanup", session), ("put_cancel",)]
