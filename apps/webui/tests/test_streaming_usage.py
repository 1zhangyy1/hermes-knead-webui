from types import SimpleNamespace

from api.streaming_usage import AgentTokenUsage, apply_agent_token_usage_to_session, build_done_usage_payload


def test_apply_agent_token_usage_overwrites_with_positive_turn_values():
    session = SimpleNamespace(
        input_tokens=9000,
        output_tokens=800,
        estimated_cost=12.34,
        cache_read_tokens=1000,
        cache_write_tokens=200,
    )
    agent = SimpleNamespace(
        session_prompt_tokens=123,
        session_completion_tokens=45,
        session_estimated_cost_usd=0.067,
        session_cache_read_tokens=9000,
        session_cache_write_tokens=1000,
    )

    usage = apply_agent_token_usage_to_session(session, agent)

    assert usage.input_tokens == 123
    assert usage.output_tokens == 45
    assert usage.estimated_cost == 0.067
    assert usage.cache_read_tokens == 9000
    assert usage.cache_write_tokens == 1000
    assert session.input_tokens == 123
    assert session.output_tokens == 45
    assert session.estimated_cost == 0.067
    assert session.cache_read_tokens == 9000
    assert session.cache_write_tokens == 1000


def test_apply_agent_token_usage_preserves_session_when_agent_values_are_empty():
    session = SimpleNamespace(
        input_tokens=9000,
        output_tokens=800,
        estimated_cost=12.34,
        cache_read_tokens=1000,
        cache_write_tokens=200,
    )
    agent = SimpleNamespace(
        session_prompt_tokens=0,
        session_completion_tokens=0,
        session_estimated_cost_usd=None,
        session_cache_read_tokens=0,
        session_cache_write_tokens=0,
    )

    usage = apply_agent_token_usage_to_session(session, agent)

    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert usage.estimated_cost is None
    assert usage.cache_read_tokens == 0
    assert usage.cache_write_tokens == 0
    assert session.input_tokens == 9000
    assert session.output_tokens == 800
    assert session.estimated_cost == 12.34
    assert session.cache_read_tokens == 1000
    assert session.cache_write_tokens == 200


def test_build_done_usage_payload_includes_terminal_fields():
    usage = build_done_usage_payload(
        AgentTokenUsage(
            input_tokens=123,
            output_tokens=45,
            estimated_cost=0.067,
            cache_read_tokens=9,
            cache_write_tokens=3,
        ),
        duration_seconds=12.3456,
        turn_tps=3.6,
        gateway_routing={'used_provider': 'provider-b'},
    )

    assert usage == {
        'input_tokens': 123,
        'output_tokens': 45,
        'estimated_cost': 0.067,
        'cache_read_tokens': 9,
        'cache_write_tokens': 3,
        'duration_seconds': 12.346,
        'tps': 3.6,
        'gateway_routing': {'used_provider': 'provider-b'},
    }
