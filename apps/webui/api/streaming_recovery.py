"""Recovery and credential self-heal helpers for streaming runs."""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class RebuiltCredentialAgent:
    agent: Any
    agent_kwargs: dict[str, Any]
    runtime: dict[str, Any]
    resolved_api_key: Any
    resolved_provider: str | None
    resolved_base_url: str | None


def materialize_pending_user_turn_before_error(session) -> bool:
    """Persist the pending user prompt before clearing runtime stream state.

    Error paths often clear ``pending_user_message`` before appending an assistant
    error marker. In deferred session-save mode that pending field can be the
    only durable copy of the user's current turn, so clearing it makes the user
    bubble disappear on reload/reconcile. Return True when a recovered user turn
    was appended.
    """
    pending_text = str(getattr(session, 'pending_user_message', None) or '')
    if not pending_text:
        return False
    normalized_pending = " ".join(pending_text.split())
    if normalized_pending:
        for existing in reversed(list(getattr(session, 'messages', None) or [])[-8:]):
            if not isinstance(existing, dict) or existing.get('role') != 'user':
                continue
            existing_text = " ".join(str(existing.get('content') or '').split())
            if existing_text == normalized_pending:
                return False
    recovered_ts = int(time.time())
    pending_started_at = getattr(session, 'pending_started_at', None)
    if isinstance(pending_started_at, (int, float)) and pending_started_at > 0:
        recovered_ts = int(pending_started_at)
    recovered = {
        'role': 'user',
        'content': pending_text,
        'timestamp': recovered_ts,
        '_recovered': True,
    }
    pending_attachments = getattr(session, 'pending_attachments', None)
    if pending_attachments:
        recovered['attachments'] = list(pending_attachments)
    session.messages.append(recovered)
    return True


def last_resort_sync_from_core(
    session,
    stream_id,
    agent_lock,
    *,
    cancel_flags,
    get_profile_home,
    apply_core_sync_or_error_marker,
    logger,
) -> None:
    """Sync from the core transcript or append a recovery marker on final exit."""
    try:
        if stream_id in cancel_flags and cancel_flags[stream_id].is_set():
            return

        profile_home = get_profile_home(session.profile)
        core_path = profile_home / 'sessions' / f'session_{session.session_id}.json'

        lock_ctx = agent_lock if agent_lock is not None else contextlib.nullcontext()
        with lock_ctx:
            apply_core_sync_or_error_marker(
                session,
                core_path,
                stream_id_for_recheck=stream_id,
                require_stream_dead=False,
            )
    except Exception:
        logger.exception(
            "_last_resort_sync_from_core failed for session %s",
            getattr(session, 'session_id', '?'),
        )


def attempt_credential_self_heal(provider_id, session_id, _agent_lock_ref, *, logger):
    """Try to silently refresh credentials after a 401/auth error (#1401)."""
    try:
        from api.oauth import (
            read_auth_json,
            resolve_runtime_provider_with_anthropic_env_lock,
        )
        from api.config import (
            SESSION_AGENT_CACHE, SESSION_AGENT_CACHE_LOCK,
            invalidate_credential_pool_cache,
        )
        from hermes_cli.runtime_provider import resolve_runtime_provider

        fresh_auth = read_auth_json()
        if not fresh_auth:
            logger.debug('[webui] self-heal: auth.json empty or missing, skipping')
            return None

        with SESSION_AGENT_CACHE_LOCK:
            SESSION_AGENT_CACHE.pop(session_id, None)

        invalidate_credential_pool_cache(provider_id)

        new_rt = resolve_runtime_provider_with_anthropic_env_lock(
            resolve_runtime_provider,
            requested=provider_id,
        )

        logger.info(
            '[webui] self-heal: credential refresh succeeded for provider=%s session=%s',
            provider_id, session_id,
        )
        return new_rt
    except Exception as heal_err:
        logger.warning(
            '[webui] self-heal: failed for provider=%s session=%s: %s',
            provider_id, session_id, heal_err,
        )
        return None


def rebuild_agent_for_credential_self_heal(
    *,
    agent_factory,
    agent_kwargs: dict[str, Any],
    agent_params,
    heal_runtime: dict[str, Any],
    resolved_model: str | None,
    resolved_provider: str | None,
    resolved_base_url: str | None,
    custom_provider_resolver,
    session_id: str,
    stream_id: str,
    agent_instances,
    streams_lock,
    ephemeral: bool,
    agent_sig: str | None,
) -> RebuiltCredentialAgent:
    """Rebuild the streaming agent after credentials are refreshed."""
    runtime = heal_runtime or {}
    resolved_api_key = runtime.get('api_key')
    if not resolved_provider:
        resolved_provider = runtime.get('provider')
    if not resolved_base_url:
        resolved_base_url = runtime.get('base_url')
    if isinstance(resolved_provider, str) and resolved_provider.startswith('custom:'):
        custom_key, custom_base = custom_provider_resolver(resolved_provider)
        if not resolved_api_key and custom_key:
            resolved_api_key = custom_key
        if not resolved_base_url and custom_base:
            resolved_base_url = custom_base

    rebuilt_kwargs = dict(agent_kwargs)
    rebuilt_kwargs['api_key'] = resolved_api_key
    rebuilt_kwargs['base_url'] = resolved_base_url
    rebuilt_kwargs['model'] = resolved_model
    rebuilt_kwargs['provider'] = resolved_provider
    if 'credential_pool' in agent_params:
        rebuilt_kwargs['credential_pool'] = runtime.get('credential_pool')

    agent = agent_factory(**rebuilt_kwargs)
    with streams_lock:
        agent_instances[stream_id] = agent

    if not ephemeral and agent_sig is not None:
        from api.config import SESSION_AGENT_CACHE, SESSION_AGENT_CACHE_LOCK

        with SESSION_AGENT_CACHE_LOCK:
            SESSION_AGENT_CACHE[session_id] = (agent, agent_sig)
            SESSION_AGENT_CACHE.move_to_end(session_id)

    return RebuiltCredentialAgent(
        agent=agent,
        agent_kwargs=rebuilt_kwargs,
        runtime=runtime,
        resolved_api_key=resolved_api_key,
        resolved_provider=resolved_provider,
        resolved_base_url=resolved_base_url,
    )
