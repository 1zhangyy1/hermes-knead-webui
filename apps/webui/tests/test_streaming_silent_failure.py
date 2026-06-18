from types import SimpleNamespace

from api.streaming_silent_failure import handle_silent_failure_after_merge
from api.streaming_turn_writeback import SilentFailureDetectionState


class Session:
    session_id = 'sid-1'


class CancelEvent:
    def __init__(self, is_set=False):
        self._is_set = is_set

    def is_set(self):
        return self._is_set


def _base_kwargs(events, **overrides):
    kwargs = {
        'agent': 'agent',
        'result': {'messages': []},
        'self_healed': False,
        'session': Session(),
        'stream_id': 'stream-1',
        'cancel_event': CancelEvent(False),
        'finalize_cancelled_turn': lambda session, *, ephemeral: events.append(
            ('finalize_cancel', session.session_id, ephemeral)
        ),
        'append_interrupted_turn_event': lambda session_id, stream_id, *, logger: events.append(
            ('append_interrupted', session_id, stream_id)
        ),
        'put_cancel': lambda: events.append(('put_cancel',)),
        'ephemeral': False,
        'classify_provider_error': lambda *_args, **_kwargs: {},
        'provider_error_payload': lambda message, error_type, hint: {
            'message': message,
            'type': error_type,
            'hint': hint,
        },
        'finalize_product_turn': lambda **kwargs: events.append(('finalize_product', kwargs)),
        'materialize_pending_user_turn': lambda session: events.append(('materialize', session.session_id)),
        'put': lambda event, payload: events.append(('put', event, payload)),
        'provider_id': 'provider-a',
        'session_id': 'sid-1',
        'agent_lock': 'lock',
        'agent_factory': object(),
        'agent_kwargs': {'existing': True},
        'agent_params': {},
        'resolved_model': 'model-a',
        'resolved_provider': 'provider-a',
        'resolved_base_url': 'https://provider.test',
        'custom_provider_resolver': lambda provider: (None, None),
        'agent_instances': {},
        'streams_lock': object(),
        'agent_sig': 'sig',
        'user_message': {'role': 'user', 'content': 'hello'},
        'system_message': 'system',
        'previous_messages': [{'role': 'system', 'content': 'old display'}],
        'previous_context_messages': [{'role': 'user', 'content': 'hello'}],
        'config': {'cfg': True},
        'persist_user_message': 'hello',
        'sanitize_messages_for_api': lambda messages, *, cfg: messages,
        'output_bridge': SimpleNamespace(token_sent=False),
        'msg_text': 'hello',
        'has_new_assistant_reply': lambda *_args: False,
        'apply_agent_result_to_session': lambda *_args, **_kwargs: events.append(('apply_result',)),
        'logger': SimpleNamespace(info=lambda *_args, **_kwargs: None),
    }
    kwargs.update(overrides)
    return kwargs


def _silent_failure_state(*, should_handle=True, assistant_added=False):
    return SilentFailureDetectionState(
        previous_context_count=1,
        assistant_added=assistant_added,
        token_sent=False,
        should_handle=should_handle,
    )


def test_handle_silent_failure_skips_when_detection_does_not_request_handling():
    events = []

    result = handle_silent_failure_after_merge(
        _silent_failure_state(should_handle=False, assistant_added=True),
        **_base_kwargs(events),
    )

    assert result.should_return is False
    assert result.assistant_added is True
    assert events == []


def test_handle_silent_failure_prioritizes_cancel_before_provider_error():
    events = []

    result = handle_silent_failure_after_merge(
        _silent_failure_state(),
        **_base_kwargs(
            events,
            cancel_event=CancelEvent(True),
            classify_silent_failure_error_fn=lambda *_args, **_kwargs: events.append(('classify',)),
            emit_and_persist_silent_failure_error_fn=lambda *_args, **_kwargs: events.append(('emit',)),
        ),
    )

    assert result.should_return is True
    assert events == [
        ('finalize_cancel', 'sid-1', False),
        ('append_interrupted', 'sid-1', 'stream-1'),
        ('put_cancel',),
    ]


def test_handle_silent_failure_emits_and_returns_for_unhealed_error():
    events = []
    silent_error = SimpleNamespace(is_auth=False)

    result = handle_silent_failure_after_merge(
        _silent_failure_state(),
        **_base_kwargs(
            events,
            classify_silent_failure_error_fn=lambda agent, result, *, classify_provider_error: silent_error,
            emit_and_persist_silent_failure_error_fn=lambda session, state, **kwargs: events.append(
                ('emit', session.session_id, state, sorted(kwargs))
            ),
        ),
    )

    assert result.should_return is True
    assert events == [(
        'emit',
        'sid-1',
        silent_error,
        [
            'finalize_product_turn',
            'logger',
            'materialize_pending_user_turn',
            'provider_error_payload',
            'put',
        ],
    )]


def test_handle_silent_failure_successful_auth_self_heal_skips_error_emission():
    events = []
    silent_error = SimpleNamespace(is_auth=True)

    def self_heal(**kwargs):
        assert kwargs['previous_messages'] == [{'role': 'system', 'content': 'old display'}]
        assert kwargs['prev_len'] == 1
        return SimpleNamespace(
            self_healed=True,
            succeeded=True,
            result={'messages': [{'role': 'assistant', 'content': 'ok'}]},
            agent='healed-agent',
            agent_kwargs={'api_key': 'fresh'},
            runtime={'provider': 'provider-b'},
            resolved_api_key='fresh-key',
            resolved_provider='provider-b',
            resolved_base_url='https://fresh.test',
        )

    result = handle_silent_failure_after_merge(
        _silent_failure_state(),
        **_base_kwargs(
            events,
            classify_silent_failure_error_fn=lambda agent, result, *, classify_provider_error: silent_error,
            handle_silent_failure_credential_self_heal_fn=self_heal,
            emit_and_persist_silent_failure_error_fn=lambda *_args, **_kwargs: events.append(('emit',)),
        ),
    )

    assert result.should_return is False
    assert result.assistant_added is True
    assert result.self_healed is True
    assert result.self_heal_succeeded is True
    assert result.result == {'messages': [{'role': 'assistant', 'content': 'ok'}]}
    assert result.agent == 'healed-agent'
    assert result.agent_kwargs == {'api_key': 'fresh'}
    assert result.runtime == {'provider': 'provider-b'}
    assert result.resolved_api_key == 'fresh-key'
    assert result.resolved_provider == 'provider-b'
    assert result.resolved_base_url == 'https://fresh.test'
    assert events == []
