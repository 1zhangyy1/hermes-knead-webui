"""Completed-turn metadata helpers for WebUI streaming workers."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class CompletedTurnMetadata:
    duration_seconds: float
    turn_tps: float | None
    gateway_routing: dict | None


def attach_reasoning_trace_to_last_assistant(messages, reasoning_text) -> bool:
    """Attach streamed reasoning text to the last assistant message before save."""
    if not reasoning_text or not messages:
        return False
    for message in reversed(messages):
        if isinstance(message, dict) and message.get('role') == 'assistant':
            message['reasoning'] = reasoning_text
            return True
    return False


def apply_completed_turn_metadata(
    session,
    agent,
    result,
    *,
    turn_started_at,
    output_tokens: int,
    requested_model: str,
    requested_provider: str,
    extract_gateway_routing_metadata: Callable[..., dict | None],
) -> CompletedTurnMetadata:
    """Persist duration/TPS/gateway metadata for the completed assistant turn."""
    try:
        duration_seconds = max(0.0, time.time() - float(turn_started_at))
    except Exception:
        duration_seconds = 0.0

    turn_tps = None
    if output_tokens and duration_seconds > 0:
        turn_tps = round(float(output_tokens) / duration_seconds, 1)

    gateway_routing = extract_gateway_routing_metadata(
        agent,
        result,
        requested_model=requested_model,
        requested_provider=requested_provider,
    )
    if gateway_routing:
        session.gateway_routing = gateway_routing
        history = list(getattr(session, 'gateway_routing_history', None) or [])
        history.append(gateway_routing)
        session.gateway_routing_history = history[-50:]

    if getattr(session, 'messages', None):
        for message in reversed(session.messages):
            if isinstance(message, dict) and message.get('role') == 'assistant':
                message['_turnDuration'] = round(duration_seconds, 3)
                if turn_tps is not None:
                    message['_turnTps'] = turn_tps
                if gateway_routing:
                    message['_gatewayRouting'] = gateway_routing
                break

    return CompletedTurnMetadata(
        duration_seconds=duration_seconds,
        turn_tps=turn_tps,
        gateway_routing=gateway_routing,
    )
