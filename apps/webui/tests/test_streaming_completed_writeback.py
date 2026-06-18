from types import SimpleNamespace

from api.streaming_completed_writeback import handle_completed_conversation_writeback


class Lock:
    def __init__(self, events):
        self.events = events

    def __enter__(self):
        self.events.append('lock-enter')

    def __exit__(self, exc_type, exc, tb):
        self.events.append('lock-exit')


class Session:
    session_id = 'sid-1'


class CancelEvent:
    def is_set(self):
        return False


def _silent_result(**overrides):
    result = {
        'self_healed': False,
        'should_return': False,
        'result': None,
        'agent': None,
        'agent_kwargs': None,
        'runtime': None,
        'resolved_api_key': None,
        'resolved_provider': None,
        'resolved_base_url': None,
    }
    result.update(overrides)
    return SimpleNamespace(**result)


def _base_kwargs(events, **overrides):
    kwargs = {
        'session': Session(),
        'agent': 'agent',
        'self_healed': False,
        'stream_id': 'stream-1',
        'session_id': 'sid-1',
        'cancel_event': CancelEvent(),
        'agent_lock': Lock(events),
        'ephemeral': False,
        'previous_messages': [{'role': 'system', 'content': 'display'}],
        'previous_context_messages': [{'role': 'user', 'content': 'hello'}],
        'msg_text': 'hello',
        'output_bridge': SimpleNamespace(token_sent=False, reasoning_text='think'),
        'live_tool_calls': [],
        'turn_started_at': 123,
        'attachments': [],
        'model': 'fallback-model',
        'resolved_model': 'model-a',
        'resolved_provider': 'provider-a',
        'resolved_base_url': 'https://old.test',
        'resolved_profile_name': 'profile-a',
        'config': {'cfg': True},
        'pre_compression_count': 3,
        'usage_snapshot': {'tokens': 9},
        'agent_factory': object(),
        'agent_kwargs': {'api_key': 'old'},
        'agent_params': {},
        'agent_sig': 'sig',
        'user_message': {'role': 'user', 'content': 'hello'},
        'system_message': 'system',
        'custom_provider_resolver': lambda provider: (None, None),
        'agent_instances': {},
        'streams_lock': object(),
        'put': lambda event, payload: events.append(('put', event, payload)),
        'finalize_cancelled_turn': lambda *_args, **_kwargs: events.append(('finalize_cancel',)),
        'append_interrupted_turn_event': lambda *_args, **_kwargs: events.append(('append_interrupted',)),
        'put_cancel': lambda: events.append(('put_cancel',)),
        'stream_writeback_is_current': lambda *_args: True,
        'classify_provider_error': lambda *_args, **_kwargs: {},
        'provider_error_payload': lambda message, error_type, hint: {},
        'finalize_product_turn': lambda **kwargs: events.append(('finalize_product', kwargs)),
        'materialize_pending_user_turn': lambda session: events.append(('materialize', session.session_id)),
        'sanitize_messages_for_api': lambda messages, *, cfg: messages,
        'has_new_assistant_reply': lambda *_args: True,
        'assistant_reply_added_after_current_turn': lambda *_args: True,
        'preserve_pre_compression_snapshot': lambda *_args, **_kwargs: events.append(('preserve',)),
        'compression_anchor_message_key': lambda message: 'key',
        'compact_summary_text': lambda text: text,
        'compression_summary_from_messages': lambda messages: 'summary',
        'title_from_fn': lambda session: None,
        'is_provisional_title': lambda *_args: False,
        'looks_invalid_generated_title': lambda *_args: False,
        'first_exchange_snippets': lambda *_args: ('hello', 'ok'),
        'extract_gateway_routing_metadata': lambda *_args: {},
        'logger': SimpleNamespace(info=lambda *_args, **_kwargs: None),
    }
    kwargs.update(overrides)
    return kwargs


def test_completed_writeback_returns_before_merge_when_guard_fails():
    events = []

    result = handle_completed_conversation_writeback(
        {'messages': [{'role': 'assistant', 'content': 'ok'}]},
        **_base_kwargs(
            events,
            prepare_success_turn_writeback_fn=lambda *args, **kwargs: events.append('prepare') or False,
            apply_agent_result_to_session_fn=lambda *args, **kwargs: events.append('merge'),
        ),
    )

    assert result.should_return is True
    assert events == ['lock-enter', 'prepare', 'lock-exit']


def test_completed_writeback_orders_merge_silent_compression_state_and_save():
    events = []
    completed_state = SimpleNamespace(token_usage='usage')

    result = handle_completed_conversation_writeback(
        {'messages': [{'role': 'assistant', 'content': 'ok'}]},
        **_base_kwargs(
            events,
            prepare_success_turn_writeback_fn=lambda *args, **kwargs: events.append('prepare') or True,
            apply_agent_result_to_session_fn=lambda *args, **kwargs: events.append('merge'),
            detect_silent_failure_after_merge_fn=lambda *args, **kwargs: events.append('detect-silent') or SimpleNamespace(
                assistant_added=True,
                should_handle=False,
                previous_context_count=1,
            ),
            handle_silent_failure_after_merge_fn=lambda *args, **kwargs: events.append('handle-silent') or _silent_result(),
            apply_streaming_context_compression_side_effects_fn=lambda *args, **kwargs: events.append('compression'),
            apply_completed_turn_writeback_state_fn=lambda *args, **kwargs: events.append('writeback-state') or completed_state,
            save_completed_turn_and_journal_fn=lambda *args, **kwargs: events.append('save') or True,
        ),
    )

    assert result.should_return is False
    assert result.completed_turn_state is completed_state
    assert events == [
        'lock-enter',
        'prepare',
        'merge',
        'detect-silent',
        'handle-silent',
        'compression',
        'writeback-state',
        'save',
        'lock-exit',
    ]


def test_completed_writeback_continues_with_healed_agent_and_result():
    events = []
    healed_result = {'messages': [{'role': 'assistant', 'content': 'healed'}]}
    completed_state = SimpleNamespace(token_usage='usage')

    def apply_completed(session, agent, result, **kwargs):
        events.append(('writeback-state', agent, result))
        return completed_state

    result = handle_completed_conversation_writeback(
        {'messages': []},
        **_base_kwargs(
            events,
            prepare_success_turn_writeback_fn=lambda *args, **kwargs: True,
            apply_agent_result_to_session_fn=lambda *args, **kwargs: None,
            detect_silent_failure_after_merge_fn=lambda *args, **kwargs: SimpleNamespace(
                assistant_added=False,
                should_handle=True,
                previous_context_count=1,
            ),
            handle_silent_failure_after_merge_fn=lambda *args, **kwargs: _silent_result(
                self_healed=True,
                result=healed_result,
                agent='healed-agent',
                agent_kwargs={'api_key': 'fresh'},
                runtime={'provider': 'provider-b'},
                resolved_api_key='fresh-key',
                resolved_provider='provider-b',
                resolved_base_url='https://fresh.test',
            ),
            apply_streaming_context_compression_side_effects_fn=lambda *args, **kwargs: events.append(('compression', kwargs['resolved_profile_name'])),
            apply_completed_turn_writeback_state_fn=apply_completed,
            save_completed_turn_and_journal_fn=lambda *args, **kwargs: True,
        ),
    )

    assert result.self_healed is True
    assert result.result is healed_result
    assert result.agent == 'healed-agent'
    assert result.agent_kwargs == {'api_key': 'fresh'}
    assert result.runtime == {'provider': 'provider-b'}
    assert result.resolved_api_key == 'fresh-key'
    assert result.resolved_provider == 'provider-b'
    assert result.resolved_base_url == 'https://fresh.test'
    assert result.completed_turn_state is completed_state
    assert ('writeback-state', 'healed-agent', healed_result) in events
