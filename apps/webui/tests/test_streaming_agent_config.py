from api.streaming_agent_config import (
    build_agent_kwargs,
    initialize_session_db,
    resolve_agent_runtime_connection,
    resolve_fallback_config,
    resolve_max_iterations_config,
    resolve_max_tokens_config,
    resolve_reasoning_config,
)


def test_initialize_session_db_returns_created_db():
    db = object()

    assert initialize_session_db(session_db_factory=lambda: db) is db


def test_initialize_session_db_warns_and_returns_none_on_failure():
    warnings = []

    def fail():
        raise RuntimeError("missing state")

    result = initialize_session_db(
        session_db_factory=fail,
        warning_fn=lambda message, *, flush=False: warnings.append((message, flush)),
    )

    assert result is None
    assert warnings == [
        (
            "[webui] WARNING: SessionDB init failed — session_search will be unavailable: missing state",
            True,
        )
    ]


def test_resolve_agent_runtime_connection_uses_runtime_provider_values_when_missing():
    runtime = {
        "api_key": "runtime-key",
        "provider": "openai",
        "base_url": "https://api.example",
    }

    result = resolve_agent_runtime_connection(
        resolved_provider=None,
        resolved_base_url=None,
        custom_provider_resolver=lambda _provider: (_ for _ in ()).throw(AssertionError("custom")),
        oauth_runtime_resolver=lambda resolver, *, requested=None: runtime,
        runtime_provider_resolver=object(),
    )

    assert result == (runtime, "runtime-key", "openai", "https://api.example")


def test_resolve_agent_runtime_connection_keeps_explicit_provider_and_base_url():
    runtime = {
        "api_key": "runtime-key",
        "provider": "ignored-provider",
        "base_url": "https://ignored.example",
    }

    result = resolve_agent_runtime_connection(
        resolved_provider="anthropic",
        resolved_base_url="https://explicit.example",
        custom_provider_resolver=lambda _provider: (_ for _ in ()).throw(AssertionError("custom")),
        oauth_runtime_resolver=lambda resolver, *, requested=None: runtime,
        runtime_provider_resolver=object(),
    )

    assert result == (runtime, "runtime-key", "anthropic", "https://explicit.example")


def test_resolve_agent_runtime_connection_falls_back_to_custom_provider_values():
    result = resolve_agent_runtime_connection(
        resolved_provider="custom:local",
        resolved_base_url=None,
        custom_provider_resolver=lambda provider: ("custom-key", f"https://{provider}.example"),
        oauth_runtime_resolver=lambda resolver, *, requested=None: {},
        runtime_provider_resolver=object(),
    )

    assert result == ({}, "custom-key", "custom:local", "https://custom:local.example")


def test_resolve_agent_runtime_connection_warns_when_runtime_provider_fails():
    warnings = []

    def fail(_resolver, *, requested=None):
        raise RuntimeError("oauth unavailable")

    result = resolve_agent_runtime_connection(
        resolved_provider="openai",
        resolved_base_url=None,
        custom_provider_resolver=lambda _provider: (_ for _ in ()).throw(AssertionError("custom")),
        oauth_runtime_resolver=fail,
        runtime_provider_resolver=object(),
        warning_fn=lambda message, *, flush=False: warnings.append((message, flush)),
    )

    assert result == ({}, None, "openai", None)
    assert warnings == [
        (
            "[webui] WARNING: resolve_runtime_provider failed: oauth unavailable",
            True,
        )
    ]


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
