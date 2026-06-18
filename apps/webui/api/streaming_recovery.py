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


@dataclass
class CredentialSelfHealRetry:
    rebuilt: RebuiltCredentialAgent
    result: dict[str, Any] | None
    error: Exception | None


@dataclass
class SilentFailureSelfHealResult:
    self_healed: bool = False
    succeeded: bool = False
    result: dict[str, Any] | None = None
    agent: Any = None
    agent_kwargs: dict[str, Any] | None = None
    runtime: dict[str, Any] | None = None
    resolved_api_key: Any = None
    resolved_provider: str | None = None
    resolved_base_url: str | None = None


@dataclass
class ExceptionSelfHealResult:
    self_healed: bool = False
    should_return: bool = False
    result: dict[str, Any] | None = None
    agent_kwargs: dict[str, Any] | None = None
    runtime: dict[str, Any] | None = None
    resolved_api_key: Any = None
    resolved_provider: str | None = None
    resolved_base_url: str | None = None


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


def retry_conversation_after_credential_self_heal(
    *,
    provider_id: str,
    session_id: str,
    agent_lock,
    agent_factory,
    agent_kwargs: dict[str, Any],
    agent_params,
    resolved_model: str | None,
    resolved_provider: str | None,
    resolved_base_url: str | None,
    custom_provider_resolver,
    stream_id: str,
    agent_instances,
    streams_lock,
    ephemeral: bool,
    agent_sig: str | None,
    user_message,
    system_message,
    previous_context_messages,
    config,
    persist_user_message,
    sanitize_messages_for_api,
    output_bridge=None,
    logger,
    retrying_log_message: str,
    retry_failed_log_message: str,
    attempt_self_heal_fn=attempt_credential_self_heal,
    rebuild_agent_fn=rebuild_agent_for_credential_self_heal,
) -> CredentialSelfHealRetry | None:
    """Refresh credentials, rebuild the agent, and retry the current turn once."""
    heal_runtime = attempt_self_heal_fn(
        provider_id,
        session_id,
        agent_lock,
        logger=logger,
    )
    if heal_runtime is None:
        return None

    logger.info(retrying_log_message)
    rebuilt = rebuild_agent_fn(
        agent_factory=agent_factory,
        agent_kwargs=agent_kwargs,
        agent_params=agent_params,
        heal_runtime=heal_runtime,
        resolved_model=resolved_model,
        resolved_provider=resolved_provider,
        resolved_base_url=resolved_base_url,
        custom_provider_resolver=custom_provider_resolver,
        session_id=session_id,
        stream_id=stream_id,
        agent_instances=agent_instances,
        streams_lock=streams_lock,
        ephemeral=ephemeral,
        agent_sig=agent_sig,
    )
    if output_bridge is not None:
        output_bridge.token_sent = False

    try:
        result = rebuilt.agent.run_conversation(
            user_message=user_message,
            system_message=system_message,
            conversation_history=sanitize_messages_for_api(
                previous_context_messages,
                cfg=config,
            ),
            task_id=session_id,
            persist_user_message=persist_user_message,
        )
    except Exception as exc:
        logger.warning(retry_failed_log_message, exc)
        return CredentialSelfHealRetry(rebuilt=rebuilt, result=None, error=exc)

    return CredentialSelfHealRetry(rebuilt=rebuilt, result=result, error=None)


def handle_silent_failure_credential_self_heal(
    *,
    should_attempt: bool,
    provider_id: str,
    session_id: str,
    agent_lock,
    agent_factory,
    agent_kwargs: dict[str, Any],
    agent_params,
    resolved_model: str | None,
    resolved_provider: str | None,
    resolved_base_url: str | None,
    custom_provider_resolver,
    stream_id: str,
    agent_instances,
    streams_lock,
    ephemeral: bool,
    agent_sig: str | None,
    user_message,
    system_message,
    previous_messages,
    previous_context_messages,
    config,
    persist_user_message: str,
    sanitize_messages_for_api,
    output_bridge,
    prev_len: int,
    session,
    msg_text: str,
    has_new_assistant_reply,
    apply_agent_result_to_session,
    logger,
    retry_conversation_after_credential_self_heal_fn=retry_conversation_after_credential_self_heal,
) -> SilentFailureSelfHealResult:
    """Retry a silent auth failure once and merge the retried result when it succeeds."""
    if not should_attempt:
        return SilentFailureSelfHealResult()

    heal_retry = retry_conversation_after_credential_self_heal_fn(
        provider_id=provider_id,
        session_id=session_id,
        agent_lock=agent_lock,
        agent_factory=agent_factory,
        agent_kwargs=agent_kwargs,
        agent_params=agent_params,
        resolved_model=resolved_model,
        resolved_provider=resolved_provider,
        resolved_base_url=resolved_base_url,
        custom_provider_resolver=custom_provider_resolver,
        stream_id=stream_id,
        agent_instances=agent_instances,
        streams_lock=streams_lock,
        ephemeral=ephemeral,
        agent_sig=agent_sig,
        user_message=user_message,
        system_message=system_message,
        previous_context_messages=previous_context_messages,
        config=config,
        persist_user_message=persist_user_message,
        sanitize_messages_for_api=sanitize_messages_for_api,
        output_bridge=output_bridge,
        logger=logger,
        retrying_log_message='[webui] self-heal: retrying stream after credential refresh',
        retry_failed_log_message='[webui] self-heal: retry also failed: %s',
    )
    if heal_retry is None:
        return SilentFailureSelfHealResult()

    rebuilt = heal_retry.rebuilt
    healed = SilentFailureSelfHealResult(
        self_healed=True,
        result=heal_retry.result,
        agent=rebuilt.agent,
        agent_kwargs=rebuilt.agent_kwargs,
        runtime=rebuilt.runtime,
        resolved_api_key=rebuilt.resolved_api_key,
        resolved_provider=rebuilt.resolved_provider,
        resolved_base_url=rebuilt.resolved_base_url,
    )
    if heal_retry.result is None:
        return healed

    heal_messages = heal_retry.result.get('messages') or []
    heal_ok = has_new_assistant_reply(heal_messages, prev_len) or output_bridge.token_sent
    if not heal_ok:
        return healed

    apply_agent_result_to_session(
        session,
        previous_messages,
        previous_context_messages,
        heal_retry.result.get('messages'),
        msg_text,
    )
    healed.succeeded = True
    return healed


def persist_exception_self_heal_result(
    session,
    result: dict[str, Any],
    *,
    previous_messages,
    previous_context_messages,
    msg_text: str,
    session_id: str,
    stream_id: str,
    ephemeral: bool,
    agent_lock,
    checkpoint_stop,
    checkpoint_thread,
    stop_checkpoint_thread,
    stream_writeback_is_current,
    apply_agent_result_to_session,
    logger,
) -> bool:
    """Persist a successful exception-path self-heal retry result.

    Return False when the worker no longer owns the stream writeback and the
    caller should return without logging retry success.
    """
    if session is None:
        return True

    stop_checkpoint_thread(checkpoint_stop, checkpoint_thread)
    lock_ctx = agent_lock if agent_lock is not None else contextlib.nullcontext()
    with lock_ctx:
        if not ephemeral and not stream_writeback_is_current(session, stream_id):
            logger.info(
                "Skipping stale stream self-heal writeback for session %s stream %s; active_stream_id=%s",
                getattr(session, 'session_id', session_id),
                stream_id,
                getattr(session, 'active_stream_id', None),
            )
            return False
        apply_agent_result_to_session(
            session,
            previous_messages,
            previous_context_messages,
            result.get('messages'),
            msg_text,
        )
        session.save()
    return True


def handle_exception_credential_self_heal(
    *,
    provider_id: str,
    session_id: str,
    agent_lock,
    agent_factory,
    agent_kwargs: dict[str, Any],
    agent_params,
    resolved_model: str | None,
    resolved_provider: str | None,
    resolved_base_url: str | None,
    custom_provider_resolver,
    stream_id: str,
    agent_instances,
    streams_lock,
    ephemeral: bool,
    agent_sig: str | None,
    user_message,
    system_message,
    previous_messages,
    previous_context_messages,
    config,
    persist_user_message: str,
    sanitize_messages_for_api,
    output_bridge,
    session,
    msg_text: str,
    checkpoint_stop,
    checkpoint_thread,
    stop_checkpoint_thread,
    stream_writeback_is_current,
    apply_agent_result_to_session,
    logger,
    retry_conversation_after_credential_self_heal_fn=retry_conversation_after_credential_self_heal,
    persist_self_heal_result_fn=persist_exception_self_heal_result,
) -> ExceptionSelfHealResult:
    """Retry an exception-path auth failure and persist the successful retry result."""
    heal_retry = retry_conversation_after_credential_self_heal_fn(
        provider_id=provider_id,
        session_id=session_id,
        agent_lock=agent_lock,
        agent_factory=agent_factory,
        agent_kwargs=agent_kwargs,
        agent_params=agent_params,
        resolved_model=resolved_model,
        resolved_provider=resolved_provider,
        resolved_base_url=resolved_base_url,
        custom_provider_resolver=custom_provider_resolver,
        stream_id=stream_id,
        agent_instances=agent_instances,
        streams_lock=streams_lock,
        ephemeral=ephemeral,
        agent_sig=agent_sig,
        user_message=user_message,
        system_message=system_message,
        previous_context_messages=previous_context_messages,
        config=config,
        persist_user_message=persist_user_message,
        sanitize_messages_for_api=sanitize_messages_for_api,
        output_bridge=output_bridge,
        logger=logger,
        retrying_log_message='[webui] self-heal (except path): retrying stream after credential refresh',
        retry_failed_log_message='[webui] self-heal (except path): retry failed: %s',
    )
    if heal_retry is None:
        return ExceptionSelfHealResult()

    rebuilt = heal_retry.rebuilt
    healed = ExceptionSelfHealResult(
        self_healed=True,
        result=heal_retry.result,
        agent_kwargs=rebuilt.agent_kwargs,
        runtime=rebuilt.runtime,
        resolved_api_key=rebuilt.resolved_api_key,
        resolved_provider=rebuilt.resolved_provider,
        resolved_base_url=rebuilt.resolved_base_url,
    )
    if heal_retry.result is None:
        return healed

    if not persist_self_heal_result_fn(
        session,
        heal_retry.result,
        previous_messages=previous_messages,
        previous_context_messages=previous_context_messages,
        msg_text=msg_text,
        session_id=session_id,
        stream_id=stream_id,
        ephemeral=ephemeral,
        agent_lock=agent_lock,
        checkpoint_stop=checkpoint_stop,
        checkpoint_thread=checkpoint_thread,
        stop_checkpoint_thread=stop_checkpoint_thread,
        stream_writeback_is_current=stream_writeback_is_current,
        apply_agent_result_to_session=apply_agent_result_to_session,
        logger=logger,
    ):
        healed.should_return = True
        return healed

    logger.info('[webui] self-heal (except path): retry succeeded')
    healed.should_return = True
    return healed
