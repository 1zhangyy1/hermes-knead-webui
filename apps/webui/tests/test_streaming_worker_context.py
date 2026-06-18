from types import SimpleNamespace

from api.streaming_worker_context import initialize_streaming_worker_context


class RunState:
    cancel_event = 'cancel-event'

    def __init__(self, events):
        self.events = events

    def put(self, event, payload):
        self.events.append(('put', event, payload))


class ProductFinalizer:
    def __init__(self, events):
        self.events = events

    def finalize(self, **kwargs):
        self.events.append(('finalize-product', kwargs))


def _base_kwargs(events, **overrides):
    kwargs = {
        'stream_id': 'stream-1',
        'session_id': 'session-1',
        'workspace': '/tmp/work',
        'model': 'model-a',
        'model_provider': 'provider-a',
        'ephemeral': False,
        'product_context': {'scope': 'product_builder', 'id': 'product-1'},
        'streams': {'stream-1': 'queue-1'},
        'get_session': lambda: 'session-object',
        'get_agent': lambda: 'agent-object',
        'logger': SimpleNamespace(
            debug=lambda *args, **kwargs: events.append(('debug', args, kwargs))
        ),
        'register_active_run_fn': lambda *args, **kwargs: events.append(
            ('register', args, kwargs)
        ),
        'run_journal_factory': lambda session_id, stream_id: events.append(
            ('journal', session_id, stream_id)
        ) or 'journal-object',
        'product_turn_finalizer_factory': lambda product_context, logger: events.append(
            ('product-finalizer', product_context)
        ) or ProductFinalizer(events),
        'append_worker_started_turn_event_fn': lambda *args, **kwargs: events.append(
            ('worker-started', args, kwargs)
        ),
        'initialize_run_state_fn': lambda **kwargs: events.append(
            (
                'run-state',
                kwargs['queue'],
                kwargs['run_journal'],
                kwargs['get_session'](),
                kwargs['get_agent'](),
            )
        ) or RunState(events),
        'time_fn': lambda: 123.0,
    }
    kwargs.update(overrides)
    return kwargs


def test_initialize_worker_context_registers_journal_and_run_state_in_order():
    events = []

    result = initialize_streaming_worker_context(**_base_kwargs(events))

    assert result.should_return is False
    assert result.cancel_event == 'cancel-event'
    assert [event[0] for event in events] == [
        'register',
        'product-finalizer',
        'journal',
        'worker-started',
        'run-state',
    ]
    assert events[0][2]['started_at'] == 123.0
    assert events[4] == ('run-state', 'queue-1', 'journal-object', 'session-object', 'agent-object')

    result.put_cancel('stop')

    assert events[-2][0] == 'finalize-product'
    assert events[-2][1]['failed'] is True
    assert events[-1] == ('put', 'cancel', {'message': 'stop'})


def test_initialize_worker_context_returns_when_stream_queue_is_missing():
    events = []

    result = initialize_streaming_worker_context(
        **_base_kwargs(events, streams={}),
    )

    assert result.should_return is True
    assert events == []


def test_initialize_worker_context_continues_when_run_journal_fails():
    events = []

    result = initialize_streaming_worker_context(
        **_base_kwargs(
            events,
            run_journal_factory=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError('journal down')
            ),
        ),
    )

    assert result.should_return is False
    assert ('run-state', 'queue-1', None, 'session-object', 'agent-object') in events
    assert any(event[0] == 'debug' for event in events)
