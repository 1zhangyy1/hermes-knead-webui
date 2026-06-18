from types import SimpleNamespace

from api.streaming_success_completion import handle_completed_conversation_success


def _turn_state():
    return SimpleNamespace(
        token_usage='usage',
        turn_metadata=SimpleNamespace(
            duration_seconds=1.5,
            turn_tps=2.0,
            gateway_routing={'provider': 'test'},
        ),
        tool_calls=[{'name': 'tool'}],
        title_plan=SimpleNamespace(
            should_background_title=False,
            user_text='hello',
            assistant_text='ok',
        ),
    )


def _writeback_result(**overrides):
    result = SimpleNamespace(
        self_healed=False,
        should_return=False,
        completed_turn_state=_turn_state(),
        result=None,
        runtime=None,
        resolved_api_key=None,
        resolved_provider=None,
        resolved_base_url=None,
        agent_kwargs=None,
        agent=None,
    )
    for key, value in overrides.items():
        setattr(result, key, value)
    return result


def _base_kwargs(events, **overrides):
    kwargs = {
        'current_result': {'messages': [{'role': 'assistant', 'content': 'old'}]},
        'runtime': {'provider': 'old-provider'},
        'resolved_api_key': 'old-key',
        'resolved_provider': 'old-provider',
        'resolved_base_url': 'https://old.test',
        'agent_kwargs': {'api_key': 'old-key'},
        'agent': 'old-agent',
        'self_healed': False,
        'session': SimpleNamespace(session_id='sid-1'),
        'original_session_id': 'sid-1',
        'config': {'agent': {}},
        'resolved_model': 'model-a',
        'profile_home': '/tmp/profile',
        'goal_related': False,
        'put': lambda event, payload: events.append(('put', event, payload)),
        'pending_goal_continuation': {},
        'redact_session_data': lambda raw: raw,
        'build_done_usage_payload': lambda *args, **kwargs: {'usage': args, **kwargs},
        'apply_context_window_to_usage': lambda *args, **kwargs: events.append('context-window'),
        'drain_pending_steer_leftover': lambda *args, **kwargs: events.append('steer-drain'),
        'run_post_turn_goal_hook': lambda *args, **kwargs: events.append('goal-hook'),
        'finalize_product_turn': lambda **kwargs: events.append(('product', kwargs)),
        'meter_stats_fn': lambda: {'tokens': 1},
        'run_background_title_update': lambda *args, **kwargs: events.append('title-update'),
        'maybe_schedule_title_refresh': lambda *args, **kwargs: events.append('title-refresh'),
        'logger': SimpleNamespace(info=lambda *_args, **_kwargs: None),
        'emit_completed_turn_done_fn': lambda *args, **kwargs: events.append(
            ('done', kwargs['agent'], kwargs['token_usage'], kwargs['resolved_provider'])
        ),
    }
    kwargs.update(overrides)
    return kwargs


def test_success_completion_emits_done_with_current_state():
    events = []

    result = handle_completed_conversation_success(
        _writeback_result(),
        **_base_kwargs(events),
    )

    assert result.should_return is False
    assert result.result == {'messages': [{'role': 'assistant', 'content': 'old'}]}
    assert result.agent == 'old-agent'
    assert events == [('done', 'old-agent', 'usage', 'old-provider')]


def test_success_completion_applies_self_healed_writeback_state_before_done():
    events = []
    healed_result = {'messages': [{'role': 'assistant', 'content': 'healed'}]}

    result = handle_completed_conversation_success(
        _writeback_result(
            self_healed=True,
            result=healed_result,
            runtime={'provider': 'new-provider'},
            resolved_api_key='new-key',
            resolved_provider='new-provider',
            resolved_base_url='https://new.test',
            agent_kwargs={'api_key': 'new-key'},
            agent='new-agent',
        ),
        **_base_kwargs(events),
    )

    assert result.self_healed is True
    assert result.result is healed_result
    assert result.runtime == {'provider': 'new-provider'}
    assert result.resolved_api_key == 'new-key'
    assert result.resolved_provider == 'new-provider'
    assert result.resolved_base_url == 'https://new.test'
    assert result.agent_kwargs == {'api_key': 'new-key'}
    assert result.agent == 'new-agent'
    assert events == [('done', 'new-agent', 'usage', 'new-provider')]


def test_success_completion_returns_without_done_when_writeback_handled_stream():
    events = []

    result = handle_completed_conversation_success(
        _writeback_result(should_return=True),
        **_base_kwargs(
            events,
            emit_completed_turn_done_fn=lambda *args, **kwargs: events.append('unexpected-done'),
        ),
    )

    assert result.should_return is True
    assert result.self_healed is False
    assert events == []
