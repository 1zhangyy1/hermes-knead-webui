"""AIAgent cache lifecycle helpers for WebUI streaming turns."""

from __future__ import annotations

from typing import Any


def handle_evicted_agent_cache_items(evicted_items: list[tuple[str, Any]], *, logger: Any | None = None) -> None:
    """Commit lifecycle state and close evicted cached agents outside the cache lock."""
    for evicted_sid, evicted_entry in evicted_items:
        try:
            evicted_agent = evicted_entry[0] if isinstance(evicted_entry, tuple) else None
            should_close_evicted_agent = True
            if evicted_agent is not None:
                try:
                    from api.session_lifecycle import (
                        commit_session_memory as _lifecycle_commit,
                        has_uncommitted_work as _lifecycle_has_uncommitted_work,
                        unregister_agent as _lifecycle_unregister_agent,
                    )
                    _lifecycle_commit(evicted_sid, agent=evicted_agent, wait=True)
                    if not _lifecycle_has_uncommitted_work(evicted_sid):
                        _lifecycle_unregister_agent(evicted_sid)
                    else:
                        should_close_evicted_agent = False
                except Exception:
                    should_close_evicted_agent = False
                    if logger is not None:
                        logger.debug("Lifecycle commit on eviction failed for %s", evicted_sid, exc_info=True)
            if (
                should_close_evicted_agent
                and evicted_agent is not None
                and getattr(evicted_agent, '_session_db', None) is not None
            ):
                evicted_agent._session_db.close()
        except Exception:
            if logger is not None:
                logger.debug("Failed to close evicted agent for session %s", evicted_sid, exc_info=True)
        if logger is not None:
            logger.debug('[webui] Evicted LRU agent from cache: %s', evicted_sid)


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
