import queue
import threading
from types import SimpleNamespace

from api.streaming_cancellation import (
    cancel_stream_request,
    handle_exception_cancel,
    handle_post_run_cancel,
    handle_preflight_cancel,
    register_agent_instance_or_cancel,
)


class _Agent:
    def __init__(self, session_id="sid-1"):
        self.session_id = session_id
        self.interrupts = []

    def interrupt(self, message):
        self.interrupts.append(message)


class _Session:
    session_id = "sid-1"


def test_cancel_stream_request_persists_cancel_and_emits_sentinel():
    stream_id = "stream-1"
    q = queue.Queue()
    flag = threading.Event()
    agent = _Agent()
    session = SimpleNamespace(active_stream_id=stream_id)
    streams = {stream_id: q}
    cancel_flags = {stream_id: flag}
    agent_instances = {stream_id: agent}
    partial_texts = {stream_id: "partial"}
    reasoning_texts = {stream_id: "thinking"}
    live_tool_calls = {stream_id: [{"name": "tool"}]}
    calls = []

    result = cancel_stream_request(
        stream_id,
        live_config=SimpleNamespace(
            STREAMS=streams,
            CANCEL_FLAGS=cancel_flags,
            AGENT_INSTANCES=agent_instances,
            STREAM_PARTIAL_TEXT=partial_texts,
            STREAM_REASONING_TEXT=reasoning_texts,
            STREAM_LIVE_TOOL_CALLS=live_tool_calls,
            STREAMS_LOCK=threading.Lock(),
        ),
        streams=streams,
        cancel_flags=cancel_flags,
        agent_instances=agent_instances,
        partial_texts=partial_texts,
        reasoning_texts=reasoning_texts,
        live_tool_calls=live_tool_calls,
        streams_lock=threading.Lock(),
        get_session=lambda session_id: calls.append(("get_session", session_id)) or session,
        get_session_agent_lock=lambda session_id: calls.append(("lock", session_id)) or threading.Lock(),
        stream_writeback_is_current=lambda session_arg, stream_id_arg: calls.append(
            ("current", session_arg, stream_id_arg)
        ) or True,
        cancelled_turn_content_fn=lambda message: f"cancelled: {message}",
        persist_cancel_stream_writeback_fn=lambda session_arg, **kwargs: calls.append(
            ("persist", session_arg, kwargs)
        ),
    )

    assert result is True
    assert flag.is_set()
    assert agent.interrupts == ["Cancelled by user"]
    assert stream_id not in streams
    assert stream_id not in cancel_flags
    assert stream_id not in agent_instances
    assert calls[:3] == [
        ("lock", "sid-1"),
        ("get_session", "sid-1"),
        ("current", session, "stream-1"),
    ]
    assert calls[3][0] == "persist"
    assert calls[3][1] is session
    assert calls[3][2]["partial_text"] == "partial"
    assert calls[3][2]["reasoning_text"] == "thinking"
    assert calls[3][2]["tool_calls"] == [{"name": "tool"}]
    assert calls[3][2]["cancelled_turn_content_fn"]("x") == "cancelled: x"
    assert calls[3][2]["logger"] is None
    assert calls[3][2]["session_id"] == "sid-1"
    event, data = q.get_nowait()
    assert event == "cancel"
    assert data == {"message": "Cancelled by user"}


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


def test_handle_preflight_cancel_returns_false_when_not_cancelled():
    cancel_event = threading.Event()

    assert handle_preflight_cancel(
        cancel_event,
        _Session(),
        threading.Lock(),
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("finalize")),
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("put")),
        ephemeral=False,
    ) is False


def test_handle_preflight_cancel_finalizes_before_start_with_message():
    cancel_event = threading.Event()
    cancel_event.set()
    session = _Session()
    calls = []

    ok = handle_preflight_cancel(
        cancel_event,
        session,
        threading.Lock(),
        lambda session_arg, *, ephemeral=False, message='': calls.append(
            ("finalize", session_arg, ephemeral, message)
        ),
        lambda message: calls.append(("put_cancel", message)),
        ephemeral=True,
    )

    assert ok is True
    assert calls == [
        ("finalize", session, True, 'Task cancelled before start.'),
        ("put_cancel", "Cancelled before start"),
    ]


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


def test_handle_exception_cancel_returns_false_when_not_cancelled():
    cancel_event = threading.Event()

    assert handle_exception_cancel(
        cancel_event,
        _Session(),
        "stream-1",
        threading.Lock(),
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("finalize")),
        lambda: (_ for _ in ()).throw(AssertionError("put")),
        ephemeral=False,
        append_interrupted_turn_event_fn=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("append")),
    ) is False


def test_handle_exception_cancel_without_session_only_emits_cancel():
    cancel_event = threading.Event()
    cancel_event.set()
    calls = []

    ok = handle_exception_cancel(
        cancel_event,
        None,
        "stream-1",
        None,
        lambda *args, **kwargs: calls.append(("finalize",)),
        lambda: calls.append(("put_cancel",)),
        ephemeral=False,
        stop_checkpoint_thread_fn=lambda *args, **kwargs: calls.append(("stop",)),
        append_interrupted_turn_event_fn=lambda *args, **kwargs: calls.append(("interrupted",)),
    )

    assert ok is True
    assert calls == [("put_cancel",)]


def test_handle_exception_cancel_stops_checkpoint_and_persists_interrupted_turn():
    cancel_event = threading.Event()
    cancel_event.set()
    session = _Session()
    calls = []

    ok = handle_exception_cancel(
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
        append_interrupted_turn_event_fn=lambda session_id, stream_id, logger=None: calls.append(
            ("interrupted", session_id, stream_id)
        ),
    )

    assert ok is True
    assert calls == [
        ("stop", "stop", "thread"),
        ("finalize", session, False),
        ("interrupted", "sid-1", "stream-1"),
        ("put_cancel",),
    ]


def test_handle_exception_cancel_ephemeral_skips_interrupted_event():
    cancel_event = threading.Event()
    cancel_event.set()
    session = _Session()
    calls = []

    ok = handle_exception_cancel(
        cancel_event,
        session,
        "stream-1",
        threading.Lock(),
        lambda session_arg, *, ephemeral=False: calls.append(("finalize", session_arg, ephemeral)),
        lambda: calls.append(("put_cancel",)),
        ephemeral=True,
        append_interrupted_turn_event_fn=lambda *args, **kwargs: calls.append(("interrupted",)),
    )

    assert ok is True
    assert calls == [("finalize", session, True), ("put_cancel",)]
