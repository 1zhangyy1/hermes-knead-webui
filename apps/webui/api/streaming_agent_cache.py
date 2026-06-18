"""AIAgent cache lifecycle helpers for WebUI streaming turns."""

from __future__ import annotations

from typing import Any


def refresh_cached_agent_for_turn(
    agent: Any,
    agent_kwargs: dict[str, Any],
    *,
    session_db: Any | None = None,
    logger: Any | None = None,
) -> Any:
    """Refresh request-scoped callbacks and per-turn state on a reused agent."""
    agent.stream_delta_callback = agent_kwargs.get('stream_delta_callback')
    agent.tool_progress_callback = agent_kwargs.get('tool_progress_callback')
    if hasattr(agent, 'tool_start_callback'):
        agent.tool_start_callback = agent_kwargs.get('tool_start_callback')
    if hasattr(agent, 'tool_complete_callback'):
        agent.tool_complete_callback = agent_kwargs.get('tool_complete_callback')
    if hasattr(agent, 'status_callback'):
        agent.status_callback = agent_kwargs.get('status_callback')
    if hasattr(agent, 'interim_assistant_callback'):
        agent.interim_assistant_callback = agent_kwargs.get('interim_assistant_callback')
    if hasattr(agent, 'reasoning_callback'):
        agent.reasoning_callback = agent_kwargs.get('reasoning_callback')
    if hasattr(agent, 'clarify_callback'):
        agent.clarify_callback = agent_kwargs.get('clarify_callback')

    if session_db is not None:
        previous_session_db = getattr(agent, '_session_db', None)
        if previous_session_db is not None and previous_session_db is not session_db:
            try:
                previous_session_db.close()
            except Exception:
                if logger is not None:
                    logger.debug("Failed to close replaced SessionDB on cached agent", exc_info=True)
        agent._session_db = session_db

    if hasattr(agent, '_api_call_count'):
        agent._api_call_count = 0
    if hasattr(agent, '_interrupted'):
        agent._interrupted = False
    if hasattr(agent, '_interrupt_message'):
        agent._interrupt_message = None

    return agent
