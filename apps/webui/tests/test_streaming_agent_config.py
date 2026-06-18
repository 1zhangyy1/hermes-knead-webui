from api.streaming_agent_config import (
    build_agent_kwargs,
    resolve_fallback_config,
    resolve_max_iterations_config,
    resolve_max_tokens_config,
    resolve_reasoning_config,
)


def test_build_agent_kwargs_includes_supported_optional_runtime_fields():
    agent_params = {
        'reasoning_config',
        'interim_assistant_callback',
        'tool_start_callback',
        'tool_complete_callback',
        'status_callback',
        'max_iterations',
        'max_tokens',
        'api_mode',
        'acp_command',
        'acp_args',
        'credential_pool',
        'gateway_session_key',
    }
    callbacks = {
        'stream_delta_callback': object(),
        'reasoning_callback': object(),
        'tool_progress_callback': object(),
        'clarify_callback': object(),
        'interim_assistant_callback': object(),
        'tool_start_callback': object(),
        'tool_complete_callback': object(),
        'status_callback': object(),
    }

    kwargs = build_agent_kwargs(
        agent_params=agent_params,
        model='gpt-4o',
        provider='openai',
        base_url='https://api.example',
        api_key='key',
        enabled_toolsets=['terminal'],
        fallback_model={'model': 'fallback'},
        session_id='sid-1',
        session_db='db',
        max_iterations=12,
        max_tokens=2048,
        reasoning_config={'effort': 'high'},
        runtime={
            'api_mode': 'responses',
            'command': 'codex',
            'args': ['--fast'],
            'credential_pool': {'name': 'pool'},
        },
        **callbacks,
    )

    assert kwargs['model'] == 'gpt-4o'
    assert kwargs['platform'] == 'webui'
    assert kwargs['quiet_mode'] is True
    assert kwargs['enabled_toolsets'] == ['terminal']
    assert kwargs['fallback_model'] == {'model': 'fallback'}
    assert kwargs['session_id'] == 'sid-1'
    assert kwargs['session_db'] == 'db'
    assert kwargs['stream_delta_callback'] is callbacks['stream_delta_callback']
    assert kwargs['reasoning_callback'] is callbacks['reasoning_callback']
    assert kwargs['tool_progress_callback'] is callbacks['tool_progress_callback']
    assert kwargs['clarify_callback'] is callbacks['clarify_callback']
    assert kwargs['reasoning_config'] == {'effort': 'high'}
    assert kwargs['interim_assistant_callback'] is callbacks['interim_assistant_callback']
    assert kwargs['tool_start_callback'] is callbacks['tool_start_callback']
    assert kwargs['tool_complete_callback'] is callbacks['tool_complete_callback']
    assert kwargs['status_callback'] is callbacks['status_callback']
    assert kwargs['max_iterations'] == 12
    assert kwargs['max_tokens'] == 2048
    assert kwargs['api_mode'] == 'responses'
    assert kwargs['acp_command'] == 'codex'
    assert kwargs['acp_args'] == ['--fast']
    assert kwargs['credential_pool'] == {'name': 'pool'}
    assert kwargs['gateway_session_key'] == 'sid-1'


def test_build_agent_kwargs_skips_unsupported_optional_fields():
    kwargs = build_agent_kwargs(
        agent_params=set(),
        model='m',
        provider='p',
        base_url=None,
        api_key=None,
        enabled_toolsets=[],
        fallback_model=None,
        session_id='sid',
        session_db=None,
        stream_delta_callback=None,
        reasoning_callback=None,
        tool_progress_callback=None,
        clarify_callback=None,
        max_iterations=12,
        max_tokens=2048,
        reasoning_config={'effort': 'low'},
        runtime={'api_mode': 'responses', 'credential_pool': object()},
    )

    assert 'max_iterations' not in kwargs
    assert 'max_tokens' not in kwargs
    assert 'reasoning_config' not in kwargs
    assert 'api_mode' not in kwargs
    assert 'credential_pool' not in kwargs
    assert 'gateway_session_key' not in kwargs


def test_resolve_config_helpers_keep_existing_parsing_behaviour():
    assert resolve_fallback_config({
        'fallback_providers': [{'model': 'fallback', 'provider': 'openai'}],
    }) == {
        'model': 'fallback',
        'provider': 'openai',
        'base_url': None,
        'api_key': None,
        'key_env': None,
    }
    assert resolve_max_iterations_config({'agent': {'max_turns': '7'}}) == 7
    assert resolve_max_tokens_config({'agent': {'max_tokens': '1024'}}) == 1024
    assert resolve_reasoning_config(
        {'agent': {'reasoning_effort': 'high'}},
        lambda value: {'effort': value},
    ) == {'effort': 'high'}
