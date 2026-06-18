"""AIAgent cache lifecycle helpers for WebUI streaming turns."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from api.streaming_agent_runtime import agent_cache_api_key_sig


@dataclass
class AgentForTurn:
    agent: Any
    agent_sig: str | None


@dataclass
class RegisteredAgentForTurn:
    agent: Any
    agent_sig: str | None
    should_continue: bool


def build_agent_cache_signature(
    *,
    resolved_model: str | None,
    resolved_api_key: str | None,
    resolved_base_url: str | None,
    resolved_provider: str | None,
    runtime: dict[str, Any] | None,
    max_iterations: Any,
    max_tokens: Any,
    fallback_resolved: Any,
    toolsets: Any,
    reasoning_config: Any,
    profile_home: str | None,
) -> str:
    """Build the stable cache identity for a reusable WebUI AIAgent."""
    runtime = runtime or {}
    credential_pool = runtime.get('credential_pool')
    sig_blob = json.dumps([
        resolved_model or '',
        agent_cache_api_key_sig(resolved_api_key, credential_pool),
        resolved_base_url or '',
        resolved_provider or '',
        runtime.get('api_mode') or '',
        runtime.get('command') or '',
        runtime.get('args') or [],
        bool(credential_pool),
        max_iterations or '',
        max_tokens or '',
        fallback_resolved or {},
        sorted(toolsets) if toolsets else [],
        reasoning_config or {},
        # #1897: profile_home is part of the agent's identity because AIAgent
        # caches profile-scoped prompts at construction time.
        profile_home or '',
    ], sort_keys=True)
    return hashlib.sha256(sig_blob.encode()).hexdigest()[:16]


def register_agent_for_lifecycle(
    session_id: str,
    agent: Any,
    *,
    agent_kind: str,
    logger: Any | None = None,
) -> None:
    """Register an agent so lifecycle boundary commits can find it later."""
    try:
        from api.session_lifecycle import register_agent
        register_agent(session_id, agent)
    except Exception:
        if logger is not None:
            logger.debug(
                "Lifecycle register_agent failed for %s session %s",
                agent_kind,
                session_id,
                exc_info=True,
            )


def cached_agent_for_signature(session_id: str, agent_sig: str, *, logger: Any | None = None) -> Any | None:
    """Return a matching cached agent and mark it as recently used."""
    from api.config import SESSION_AGENT_CACHE, SESSION_AGENT_CACHE_LOCK

    agent = None
    with SESSION_AGENT_CACHE_LOCK:
        cached = SESSION_AGENT_CACHE.get(session_id)
        if cached and cached[1] == agent_sig:
            agent = cached[0]
            SESSION_AGENT_CACHE.move_to_end(session_id)  # LRU: mark as recently used
            if logger is not None:
                logger.debug('[webui] Reusing cached agent for session %s', session_id)
            register_agent_for_lifecycle(session_id, agent, agent_kind='cached', logger=logger)
    return agent


def refresh_or_discard_cached_agent(
    session_id: str,
    agent: Any,
    agent_kwargs: dict[str, Any],
    *,
    logger: Any | None = None,
) -> Any | None:
    """Refresh cached-agent runtime credentials or drop an unsafe cache entry."""
    from api import streaming_agent_runtime

    if streaming_agent_runtime.refresh_cached_agent_runtime(agent, agent_kwargs):
        return agent

    if logger is not None:
        logger.warning(
            '[webui] Cached agent runtime could not be safely refreshed; rebuilding agent for session %s',
            session_id,
        )
    try:
        if getattr(agent, '_session_db', None) is not None:
            agent._session_db.close()
    except Exception:
        pass

    from api.config import SESSION_AGENT_CACHE, SESSION_AGENT_CACHE_LOCK
    with SESSION_AGENT_CACHE_LOCK:
        SESSION_AGENT_CACHE.pop(session_id, None)
    return None


def cache_new_agent_for_signature(
    session_id: str,
    agent: Any,
    agent_sig: str,
    *,
    logger: Any | None = None,
) -> None:
    """Cache a newly constructed agent and handle any LRU evictions."""
    from api.config import SESSION_AGENT_CACHE, SESSION_AGENT_CACHE_LOCK, SESSION_AGENT_CACHE_MAX

    register_agent_for_lifecycle(session_id, agent, agent_kind='new', logger=logger)
    evicted_items = []
    with SESSION_AGENT_CACHE_LOCK:
        SESSION_AGENT_CACHE[session_id] = (agent, agent_sig)
        SESSION_AGENT_CACHE.move_to_end(session_id)  # LRU: mark as recently used
        while len(SESSION_AGENT_CACHE) > SESSION_AGENT_CACHE_MAX:
            evicted_sid, evicted_entry = SESSION_AGENT_CACHE.popitem(last=False)
            evicted_items.append((evicted_sid, evicted_entry))
    # Commit and close evicted agents outside the cache lock so concurrent
    # cache users are not blocked by provider I/O.
    handle_evicted_agent_cache_items(evicted_items, logger=logger)
    if logger is not None:
        logger.debug('[webui] Created new agent for session %s', session_id)


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


def get_cached_or_new_agent_for_turn(
    session_id: str,
    agent_sig: str,
    agent_kwargs: dict[str, Any],
    *,
    agent_factory,
    session_db: Any | None = None,
    cached_agent_fn=cached_agent_for_signature,
    refresh_or_discard_fn=refresh_or_discard_cached_agent,
    refresh_for_turn_fn=refresh_cached_agent_for_turn,
    cache_new_fn=cache_new_agent_for_signature,
    logger: Any | None = None,
) -> Any:
    """Return a reusable cached agent for this turn, or construct and cache one."""
    agent = cached_agent_fn(session_id, agent_sig, logger=logger)
    if agent is not None:
        # Refresh volatile runtime credentials selected from provider pools
        # without discarding cross-turn agent/provider state.
        agent = refresh_or_discard_fn(session_id, agent, agent_kwargs, logger=logger)

    if agent is not None:
        refresh_for_turn_fn(agent, agent_kwargs, session_db=session_db, logger=logger)
        return agent

    agent = agent_factory(**agent_kwargs)
    cache_new_fn(session_id, agent, agent_sig, logger=logger)
    return agent


def get_agent_for_turn(
    *,
    session_id: str,
    agent_factory,
    agent_kwargs: dict[str, Any],
    ephemeral: bool,
    resolved_model: str | None,
    resolved_api_key: str | None,
    resolved_base_url: str | None,
    resolved_provider: str | None,
    runtime: dict[str, Any] | None,
    max_iterations: Any,
    max_tokens: Any,
    fallback_resolved: Any,
    toolsets: Any,
    reasoning_config: Any,
    profile_home: str | None,
    session_db: Any | None = None,
    cache_signature_fn=build_agent_cache_signature,
    cached_or_new_fn=get_cached_or_new_agent_for_turn,
    logger: Any | None = None,
) -> AgentForTurn:
    """Return the agent for a streaming turn, using cache unless the turn is ephemeral."""
    if ephemeral:
        agent = agent_factory(**agent_kwargs)
        if logger is not None:
            logger.debug('[webui] Created ephemeral agent for session %s', session_id)
        return AgentForTurn(agent=agent, agent_sig=None)

    agent_sig = cache_signature_fn(
        resolved_model=resolved_model,
        resolved_api_key=resolved_api_key,
        resolved_base_url=resolved_base_url,
        resolved_provider=resolved_provider,
        runtime=runtime,
        max_iterations=max_iterations,
        max_tokens=max_tokens,
        fallback_resolved=fallback_resolved,
        toolsets=toolsets,
        reasoning_config=reasoning_config,
        profile_home=profile_home,
    )
    agent = cached_or_new_fn(
        session_id,
        agent_sig,
        agent_kwargs,
        agent_factory=agent_factory,
        session_db=session_db,
        logger=logger,
    )
    return AgentForTurn(agent=agent, agent_sig=agent_sig)


def get_and_register_agent_for_turn(
    *,
    session_id: str,
    stream_id: str,
    session,
    agent_factory,
    agent_kwargs: dict[str, Any],
    ephemeral: bool,
    resolved_model: str | None,
    resolved_api_key: str | None,
    resolved_base_url: str | None,
    resolved_provider: str | None,
    runtime: dict[str, Any] | None,
    max_iterations: Any,
    max_tokens: Any,
    fallback_resolved: Any,
    toolsets: Any,
    reasoning_config: Any,
    profile_home: str | None,
    session_db: Any | None,
    agent_lock,
    finalize_cancelled_turn_fn,
    put_cancel_fn,
    register_agent_instance_or_cancel_fn=None,
    get_agent_for_turn_fn=get_agent_for_turn,
    logger: Any | None = None,
) -> RegisteredAgentForTurn:
    """Return the turn agent and register it for cancel/interrupt propagation."""
    agent_for_turn = get_agent_for_turn_fn(
        session_id=session_id,
        agent_factory=agent_factory,
        agent_kwargs=agent_kwargs,
        ephemeral=ephemeral,
        resolved_model=resolved_model,
        resolved_api_key=resolved_api_key,
        resolved_base_url=resolved_base_url,
        resolved_provider=resolved_provider,
        runtime=runtime,
        max_iterations=max_iterations,
        max_tokens=max_tokens,
        fallback_resolved=fallback_resolved,
        toolsets=toolsets,
        reasoning_config=reasoning_config,
        profile_home=profile_home,
        session_db=session_db,
        logger=logger,
    )
    agent = agent_for_turn.agent
    agent_sig = agent_for_turn.agent_sig
    if register_agent_instance_or_cancel_fn is None:
        from api.streaming_cancellation import register_agent_instance_or_cancel as register_agent_instance_or_cancel_fn
    should_continue = register_agent_instance_or_cancel_fn(
        stream_id,
        agent,
        session,
        agent_lock=agent_lock,
        finalize_cancelled_turn_fn=finalize_cancelled_turn_fn,
        put_cancel_fn=put_cancel_fn,
        ephemeral=ephemeral,
        logger=logger,
    )
    return RegisteredAgentForTurn(
        agent=agent,
        agent_sig=agent_sig,
        should_continue=bool(should_continue),
    )
