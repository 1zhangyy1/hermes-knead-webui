from types import SimpleNamespace

import pytest

from api.streaming_agent_turn_setup import prepare_streaming_agent_turn_setup


class Agent:
    pass


def _bridge():
    return SimpleNamespace(
        output_bridge='output-bridge',
        tool_bridge='tool-bridge',
        live_tool_calls=['live-tool'],
        checkpoint_activity=[0],
    )


def _kwargs_state():
    return SimpleNamespace(
        agent_kwargs={'api_key': 'runtime-key'},
        agent_params={'session_db', 'status_callback'},
        fallback_resolved={'model': 'fallback'},
        max_iterations=12,
        max_tokens=4096,
        reasoning_config={'effort': 'medium'},
    )


def _registered_agent(**overrides):
    result = SimpleNamespace(agent='agent-object', agent_sig='sig-1', should_continue=True)
    for key, value in overrides.items():
        setattr(result, key, value)
    return result


def _base_kwargs(events, runtime_state=None, **overrides):
    kwargs = {
        'stream_id': 'stream-1',
        'session_id': 'session-1',
        'session': 'session-object',
        'model': 'model-a',
        'provider_context': 'provider-context',
        'profile_home': '/profiles/alpha',
        'run_state': 'run-state',
        'put': lambda event, payload: events.append(('put', event, payload)),
        'cancel_event': 'cancel-event',
        'agent_lock': 'agent-lock',
        'ephemeral': False,
        'tool_result_snippet': lambda result: str(result),
        'clarify_timeout_seconds': lambda: 120,
        'webui_clarify_callback': lambda *args, **kwargs: None,
        'finalize_cancelled_turn': lambda *args, **kwargs: events.append('finalize-cancel'),
        'put_cancel': lambda *args, **kwargs: events.append('put-cancel'),
        'get_ai_agent': lambda: Agent,
        'logger': SimpleNamespace(info=lambda *_args, **_kwargs: None),
        'runtime_state': runtime_state if runtime_state is not None else {},
        'aiagent_import_error_detail_fn': lambda: 'missing ai agent',
        'initialize_bridges_fn': lambda **kwargs: events.append(
            ('bridges', kwargs['stream_id'], kwargs['session_id'])
        ) or _bridge(),
        'initialize_session_db_fn': lambda: events.append('session-db') or 'session-db',
        'resolve_model_provider_fn': lambda value: events.append(
            ('resolve-model', value)
        ) or ('resolved-model', 'resolved-provider', 'resolved-base'),
        'model_with_provider_context_fn': lambda model, context: f'{context}:{model}',
        'resolve_agent_runtime_connection_fn': lambda **kwargs: events.append(
            ('runtime', kwargs['resolved_provider'], kwargs['resolved_base_url'])
        ) or ({'api_mode': 'responses'}, 'runtime-key', 'runtime-provider', 'runtime-base'),
        'custom_provider_resolver': lambda provider: ('custom-key', 'custom-base'),
        'load_agent_config_and_toolsets_fn': lambda session_id: events.append(
            ('config', session_id)
        ) or ({'agent': {'max_turns': 12}}, ['terminal']),
        'prepare_webui_agent_kwargs_fn': lambda **kwargs: events.append(
            (
                'kwargs',
                kwargs['agent_cls'],
                kwargs['session_db'],
                kwargs['output_bridge'],
                kwargs['tool_bridge'],
                kwargs['runtime'],
            )
        ) or _kwargs_state(),
        'get_and_register_agent_for_turn_fn': lambda **kwargs: events.append(
            (
                'register',
                kwargs['agent_factory'],
                kwargs['agent_kwargs'],
                kwargs['profile_home'],
                kwargs['max_iterations'],
                kwargs['reasoning_config'],
            )
        ) or _registered_agent(),
    }
    kwargs.update(overrides)
    return kwargs


def test_prepare_streaming_agent_turn_setup_builds_and_registers_agent():
    events = []
    runtime_state = {}

    result = prepare_streaming_agent_turn_setup(
        **_base_kwargs(events, runtime_state=runtime_state),
    )

    assert result.should_continue is True
    assert result.agent == 'agent-object'
    assert result.agent_sig == 'sig-1'
    assert result.agent_factory is Agent
    assert result.agent_kwargs == {'api_key': 'runtime-key'}
    assert result.agent_params == {'session_db', 'status_callback'}
    assert result.config == {'agent': {'max_turns': 12}}
    assert result.runtime == {'api_mode': 'responses'}
    assert result.resolved_model == 'resolved-model'
    assert result.resolved_provider == 'runtime-provider'
    assert result.resolved_base_url == 'runtime-base'
    assert result.output_bridge == 'output-bridge'
    assert result.live_tool_calls == ['live-tool']
    assert result.checkpoint_activity == [0]
    assert [event[0] if isinstance(event, tuple) else event for event in events] == [
        'bridges',
        'session-db',
        'resolve-model',
        'runtime',
        'config',
        'kwargs',
        'register',
    ]
    assert runtime_state['_output_bridge'] == 'output-bridge'
    assert runtime_state['_AIAgent'] is Agent
    assert runtime_state['_cfg'] == {'agent': {'max_turns': 12}}
    assert runtime_state['_agent_kwargs'] == {'api_key': 'runtime-key'}
    assert runtime_state['_agent_sig'] == 'sig-1'


def test_prepare_streaming_agent_turn_setup_raises_import_error_without_agent():
    events = []
    runtime_state = {}

    with pytest.raises(ImportError, match='missing ai agent'):
        prepare_streaming_agent_turn_setup(
            **_base_kwargs(
                events,
                runtime_state=runtime_state,
                get_ai_agent=lambda: None,
            ),
        )

    assert runtime_state['_output_bridge'] == 'output-bridge'
    assert runtime_state['_AIAgent'] is None
    assert [event[0] if isinstance(event, tuple) else event for event in events] == ['bridges']


def test_prepare_streaming_agent_turn_setup_returns_when_registration_cancels():
    events = []
    runtime_state = {}

    result = prepare_streaming_agent_turn_setup(
        **_base_kwargs(
            events,
            runtime_state=runtime_state,
            get_and_register_agent_for_turn_fn=lambda **kwargs: events.append('register-stop')
            or _registered_agent(should_continue=False),
        ),
    )

    assert result.should_continue is False
    assert result.agent is None
    assert runtime_state['_registered_agent'].should_continue is False
    assert runtime_state['_agent_sig'] == 'sig-1'
