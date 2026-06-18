"""Usage persistence helpers for WebUI streaming turns."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentTokenUsage:
    input_tokens: int
    output_tokens: int
    estimated_cost: float | None
    cache_read_tokens: int
    cache_write_tokens: int


def apply_agent_token_usage_to_session(session, agent) -> AgentTokenUsage:
    """Copy non-zero per-turn token usage from the agent onto the session."""
    usage = AgentTokenUsage(
        input_tokens=getattr(agent, 'session_prompt_tokens', 0) or 0,
        output_tokens=getattr(agent, 'session_completion_tokens', 0) or 0,
        estimated_cost=getattr(agent, 'session_estimated_cost_usd', None),
        cache_read_tokens=getattr(agent, 'session_cache_read_tokens', 0) or 0,
        cache_write_tokens=getattr(agent, 'session_cache_write_tokens', 0) or 0,
    )

    if usage.input_tokens > 0:
        session.input_tokens = usage.input_tokens
    if usage.output_tokens > 0:
        session.output_tokens = usage.output_tokens
    if usage.estimated_cost is not None:
        session.estimated_cost = usage.estimated_cost
    if usage.cache_read_tokens > 0:
        session.cache_read_tokens = usage.cache_read_tokens
    if usage.cache_write_tokens > 0:
        session.cache_write_tokens = usage.cache_write_tokens

    return usage


def build_done_usage_payload(
    token_usage: AgentTokenUsage,
    *,
    duration_seconds: float,
    turn_tps: float | None = None,
    gateway_routing: dict | None = None,
) -> dict:
    """Build the terminal SSE usage payload for a completed streaming turn."""
    usage = {
        'input_tokens': token_usage.input_tokens,
        'output_tokens': token_usage.output_tokens,
        'estimated_cost': token_usage.estimated_cost,
        'cache_read_tokens': token_usage.cache_read_tokens,
        'cache_write_tokens': token_usage.cache_write_tokens,
        'duration_seconds': round(duration_seconds, 3),
    }
    if turn_tps is not None:
        usage['tps'] = turn_tps
    if gateway_routing:
        usage['gateway_routing'] = gateway_routing
    return usage
