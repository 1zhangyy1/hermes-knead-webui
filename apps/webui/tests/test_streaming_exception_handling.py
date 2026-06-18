from types import SimpleNamespace

from api.streaming_exception_handling import handle_streaming_exception


class Session:
    session_id = 'sid-1'
    active_stream_id = 'stream-1'


class CancelEvent:
    def is_set(self):
        return False


def _base_kwargs(events, **overrides):
    kwargs = {
        'runtime_vars': {'msg_text': 'hello'},
        'self_healed': False,
        'session': Session(),
        'stream_id': 'stream-1',
        'session_id': 'sid-1',
        'cancel_event': CancelEvent(),
        'agent_lock': None,
        'checkpoint_stop': None,
        'checkpoint_thread': None,
        'ephemeral': False,
        'logger': SimpleNamespace(info=lambda *_args, **_kwargs: None),
        'sanitize_provider_error_text': lambda text: events.append(('sanitize', text)) or 'clean error',
        'classify_provider_error': lambda err_str, exc: events.append(
            ('classify', err_str, str(exc))
        ) or {'type': 'rate_limit'},
        'finalize_cancelled_turn': lambda *_args, **_kwargs: events.append(('finalize_cancel',)),
        'put_cancel': lambda: events.append(('put_cancel',)),
        'provider_error_payload': lambda message, error_type, hint: {
            'message': message,
            'type': error_type,
            'hint': hint,
        },
        'finalize_product_turn': lambda **kwargs: events.append(('finalize_product', kwargs)),
        'put': lambda event, payload: events.append(('put', event, payload)),
        'append_interrupted_turn_event': lambda session_id, stream_id, *, logger: events.append(
            ('append_interrupted', session_id, stream_id)
        ),
        'materialize_pending_user_turn': lambda session: events.append(('materialize', session.session_id)),
        'stop_checkpoint_thread': lambda stop, thread: events.append(('stop_checkpoint', stop, thread)),
        'stream_writeback_is_current': lambda session, stream_id: True,
        'custom_provider_resolver': lambda provider: (None, None),
        'agent_instances': {},
        'streams_lock': object(),
        'sanitize_messages_for_api': lambda messages, *, cfg: messages,
        'apply_agent_result_to_session': lambda *_args, **_kwargs: events.append(('apply_result',)),
        'agent_factory': object(),
    }
    kwargs.update(overrides)
    return kwargs


def test_handle_streaming_exception_emits_classified_error():
    events = []

    result = handle_streaming_exception(
        RuntimeError('boom'),
        **_base_kwargs(
            events,
            handle_exception_cancel_fn=lambda *_args, **_kwargs: events.append(('cancel_check',)) or False,
            exception_error_copy_fn=lambda classification: events.append(
                ('copy', classification)
            ) or ('Rate limited', classification['type'], 'Wait a bit'),
            emit_and_persist_exception_streaming_error_fn=lambda session, **kwargs: events.append(
                ('emit', session.session_id, kwargs['error_type'], kwargs['hint'])
            ) or True,
        ),
    )

    assert result.should_return is False
    assert events == [
        ('sanitize', 'boom'),
        ('classify', 'clean error', 'boom'),
        ('cancel_check',),
        ('copy', {'type': 'rate_limit'}),
        ('emit', 'sid-1', 'rate_limit', 'Wait a bit'),
    ]


def test_handle_streaming_exception_prioritizes_cancel_before_error_emit():
    events = []

    result = handle_streaming_exception(
        RuntimeError('cancelled'),
        **_base_kwargs(
            events,
            handle_exception_cancel_fn=lambda *_args, **_kwargs: events.append(('cancel_check',)) or True,
            exception_error_copy_fn=lambda *_args: events.append(('copy',)),
            emit_and_persist_exception_streaming_error_fn=lambda *_args, **_kwargs: events.append(('emit',)),
        ),
    )

    assert result.should_return is True
    assert events == [
        ('sanitize', 'cancelled'),
        ('classify', 'clean error', 'cancelled'),
        ('cancel_check',),
    ]


def test_handle_streaming_exception_auth_self_heal_updates_runtime_and_skips_emit():
    events = []
    runtime_vars = {
        'resolved_provider': 'provider-a',
        'resolved_model': 'model-a',
        'resolved_base_url': 'https://old.test',
        '_agent_kwargs': {'api_key': 'old'},
        '_agent_params': {'credential_pool': True},
        '_agent_sig': 'sig',
        'user_message': {'role': 'user', 'content': 'hello'},
        'workspace_system_msg': 'system',
        '_previous_messages': [{'role': 'system', 'content': 'display'}],
        '_previous_context_messages': [{'role': 'user', 'content': 'hello'}],
        '_cfg': {'cfg': True},
        'msg_text': 'hello',
        '_output_bridge': SimpleNamespace(token_sent=False),
    }

    def self_heal(**kwargs):
        events.append(('self_heal', kwargs['previous_messages'], kwargs['agent_kwargs']))
        return SimpleNamespace(
            self_healed=True,
            should_return=True,
            runtime={'provider': 'provider-b'},
            resolved_api_key='fresh-key',
            resolved_provider='provider-b',
            resolved_base_url='https://fresh.test',
            agent_kwargs={'api_key': 'fresh'},
        )

    result = handle_streaming_exception(
        RuntimeError('401'),
        **_base_kwargs(
            events,
            runtime_vars=runtime_vars,
            classify_provider_error=lambda err_str, exc: events.append(
                ('classify', err_str, str(exc))
            ) or {'type': 'auth_mismatch'},
            handle_exception_cancel_fn=lambda *_args, **_kwargs: events.append(('cancel_check',)) or False,
            handle_exception_credential_self_heal_fn=self_heal,
            emit_and_persist_exception_streaming_error_fn=lambda *_args, **_kwargs: events.append(('emit',)),
        ),
    )

    assert result.should_return is True
    assert result.self_healed is True
    assert result.runtime == {'provider': 'provider-b'}
    assert result.resolved_api_key == 'fresh-key'
    assert result.resolved_provider == 'provider-b'
    assert result.resolved_base_url == 'https://fresh.test'
    assert result.agent_kwargs == {'api_key': 'fresh'}
    assert events == [
        ('sanitize', '401'),
        ('classify', 'clean error', '401'),
        ('cancel_check',),
        ('self_heal', [{'role': 'system', 'content': 'display'}], {'api_key': 'old'}),
    ]


def test_handle_streaming_exception_returns_when_writeback_is_stale():
    events = []

    result = handle_streaming_exception(
        RuntimeError('stale'),
        **_base_kwargs(
            events,
            handle_exception_cancel_fn=lambda *_args, **_kwargs: False,
            exception_error_copy_fn=lambda classification: ('Error', classification['type'], ''),
            emit_and_persist_exception_streaming_error_fn=lambda *_args, **_kwargs: False,
        ),
    )

    assert result.should_return is True
