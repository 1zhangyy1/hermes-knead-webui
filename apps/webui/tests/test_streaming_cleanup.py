import api.config as cfg
from api.streaming_cleanup import (
    cleanup_stream_registries,
    finalize_streaming_run_attempt,
    finalize_streaming_worker_exit,
    finalize_webui_streaming_worker_exit,
)


class DummyLock:
    def __init__(self):
        self.entered = False
        self.exited = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc, tb):
        self.exited = True


def test_cleanup_stream_registries_removes_all_per_stream_state():
    stream_id = 'stream-1'
    registries = [{stream_id: 'value'} for _ in range(8)]
    unregistered = []
    lock = DummyLock()

    cleanup_stream_registries(
        stream_id,
        streams=registries[0],
        cancel_flags=registries[1],
        agent_instances=registries[2],
        partial_text=registries[3],
        reasoning_text=registries[4],
        live_tool_calls=registries[5],
        goal_related=registries[6],
        last_event_ids=registries[7],
        unregister_active_run=unregistered.append,
        streams_lock=lock,
    )

    assert lock.entered is True
    assert lock.exited is True
    assert all(stream_id not in registry for registry in registries)
    assert unregistered == [stream_id]


def test_cleanup_stream_registries_does_not_require_existing_keys():
    unregistered = []

    cleanup_stream_registries(
        'missing-stream',
        streams={},
        cancel_flags={},
        agent_instances={},
        partial_text={},
        reasoning_text={},
        live_tool_calls={},
        goal_related={},
        last_event_ids={},
        unregister_active_run=unregistered.append,
        streams_lock=DummyLock(),
    )

    assert unregistered == ['missing-stream']


class _Session:
    active_stream_id = 'stream-1'
    pending_user_message = 'hello'


def test_finalize_streaming_run_attempt_stops_ticker_unregisters_gateway_and_restores_env():
    events = []

    class Ticker:
        def stop(self):
            events.append('stop-ticker')

    class GatewayNotifications:
        def unregister(self, session_id):
            events.append(('unregister-gateway', session_id))

    finalize_streaming_run_attempt(
        run_state=type('RunState', (), {'metering_ticker': Ticker()})(),
        gateway_notifications=GatewayNotifications(),
        session_id='sid-1',
        profile_env_snapshot={'PROFILE_KEY': 'old'},
        runtime_env_snapshot={'HERMES_HOME': 'old-home'},
        env_lock='lock',
        restore_agent_process_env_fn=lambda profile_env, runtime_env, *, env_lock: events.append(
            ('restore-env', profile_env, runtime_env, env_lock)
        ),
    )

    assert events == [
        'stop-ticker',
        ('unregister-gateway', 'sid-1'),
        ('restore-env', {'PROFILE_KEY': 'old'}, {'HERMES_HOME': 'old-home'}, 'lock'),
    ]


def test_finalize_streaming_worker_exit_stops_checkpoint_before_recovery_and_cleans_registries():
    events = []
    registries = [{'stream-1': 'value'} for _ in range(8)]
    session = _Session()

    finalize_streaming_worker_exit(
        session=session,
        stream_id='stream-1',
        agent_lock='agent-lock',
        checkpoint_stop='stop',
        checkpoint_thread='thread',
        stop_checkpoint_thread=lambda stop, thread: events.append(('stop', stop, thread)),
        update_active_run=lambda stream_id, **kwargs: events.append(('active', stream_id, kwargs)),
        last_resort_sync_from_core=lambda session, stream_id, agent_lock: events.append(
            ('sync', session, stream_id, agent_lock)
        ),
        finalize_product_turn=lambda **kwargs: events.append(('finalize', kwargs)),
        clear_thread_env=lambda: events.append(('clear-env', None)),
        streams=registries[0],
        cancel_flags=registries[1],
        agent_instances=registries[2],
        partial_text=registries[3],
        reasoning_text=registries[4],
        live_tool_calls=registries[5],
        goal_related=registries[6],
        last_event_ids=registries[7],
        unregister_active_run=lambda stream_id: events.append(('unregister', stream_id)),
        streams_lock=DummyLock(),
    )

    assert events[:4] == [
        ('stop', 'stop', 'thread'),
        ('active', 'stream-1', {'phase': 'finalizing'}),
        ('sync', session, 'stream-1', 'agent-lock'),
        ('finalize', {'failed': True}),
    ]
    assert events[-2:] == [('clear-env', None), ('unregister', 'stream-1')]
    assert all('stream-1' not in registry for registry in registries)


def test_finalize_streaming_worker_exit_skips_recovery_without_pending_owner():
    events = []
    session = _Session()
    session.active_stream_id = 'newer-stream'

    finalize_streaming_worker_exit(
        session=session,
        stream_id='stream-1',
        agent_lock=None,
        checkpoint_stop=None,
        checkpoint_thread=None,
        stop_checkpoint_thread=lambda *_args: events.append('stop'),
        update_active_run=lambda *_args, **_kwargs: events.append('active'),
        last_resort_sync_from_core=lambda *_args: events.append('sync'),
        finalize_product_turn=lambda **kwargs: events.append(('finalize', kwargs)),
        clear_thread_env=lambda: events.append('clear-env'),
        streams={},
        cancel_flags={},
        agent_instances={},
        partial_text={},
        reasoning_text={},
        live_tool_calls={},
        goal_related={},
        last_event_ids={},
        unregister_active_run=lambda stream_id: events.append(('unregister', stream_id)),
        streams_lock=DummyLock(),
    )

    assert events == [
        'stop',
        ('finalize', {'failed': True}),
        'clear-env',
        ('unregister', 'stream-1'),
    ]


def test_finalize_webui_streaming_worker_exit_cleans_standard_registries():
    events = []
    stream_id = 'stream-webui-cleanup-wrapper'
    registries = (
        cfg.STREAMS,
        cfg.CANCEL_FLAGS,
        cfg.AGENT_INSTANCES,
        cfg.STREAM_PARTIAL_TEXT,
        cfg.STREAM_REASONING_TEXT,
        cfg.STREAM_LIVE_TOOL_CALLS,
        cfg.STREAM_GOAL_RELATED,
        cfg.STREAM_LAST_EVENT_ID,
    )

    with cfg.STREAMS_LOCK:
        for registry in registries:
            registry.pop(stream_id, None)
            registry[stream_id] = 'value'

    try:
        finalize_webui_streaming_worker_exit(
            session=None,
            stream_id=stream_id,
            agent_lock='agent-lock',
            checkpoint_stop='stop',
            checkpoint_thread='thread',
            last_resort_sync_from_core=lambda *_args: events.append('sync'),
            finalize_product_turn=lambda **kwargs: events.append(('finalize', kwargs)),
            goal_related=cfg.STREAM_GOAL_RELATED,
            stop_checkpoint_thread_fn=lambda stop, thread: events.append(('stop', stop, thread)),
            update_active_run_fn=lambda *_args, **_kwargs: events.append('active'),
            clear_thread_env_fn=lambda: events.append('clear-env'),
            unregister_active_run_fn=lambda sid: events.append(('unregister', sid)),
        )

        assert events == [
            ('stop', 'stop', 'thread'),
            ('finalize', {'failed': True}),
            'clear-env',
            ('unregister', stream_id),
        ]
        with cfg.STREAMS_LOCK:
            assert all(stream_id not in registry for registry in registries)
    finally:
        with cfg.STREAMS_LOCK:
            for registry in registries:
                registry.pop(stream_id, None)
