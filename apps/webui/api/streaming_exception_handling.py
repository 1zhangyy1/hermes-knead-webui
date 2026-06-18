"""Exception-path orchestration for WebUI streaming workers."""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Any, Callable

from api.streaming_cancellation import handle_exception_cancel
from api.streaming_error_writeback import emit_and_persist_exception_streaming_error
from api.streaming_errors import exception_error_copy
from api.streaming_recovery import handle_exception_credential_self_heal


@dataclass
class StreamingExceptionHandlingResult:
    should_return: bool = False
    self_healed: bool = False
    runtime: dict[str, Any] | None = None
    resolved_api_key: Any = None
    resolved_provider: str | None = None
    resolved_base_url: str | None = None
    agent_kwargs: dict[str, Any] | None = None


def handle_streaming_exception(
    exc: Exception,
    *,
    runtime_vars: dict[str, Any],
    self_healed: bool,
    session,
    stream_id: str,
    session_id: str,
    cancel_event,
    agent_lock,
    checkpoint_stop,
    checkpoint_thread,
    ephemeral: bool,
    logger,
    sanitize_provider_error_text: Callable[[str], str],
    classify_provider_error: Callable[..., dict],
    finalize_cancelled_turn: Callable[..., object],
    put_cancel: Callable[[], object],
    provider_error_payload: Callable[[str, str, str], dict],
    finalize_product_turn: Callable[..., object],
    put: Callable[[str, object], object],
    append_interrupted_turn_event: Callable[..., object],
    materialize_pending_user_turn: Callable[[object], object] | None,
    stop_checkpoint_thread: Callable[[object, object], object],
    stream_writeback_is_current: Callable[[object, str], bool],
    custom_provider_resolver,
    agent_instances,
    streams_lock,
    sanitize_messages_for_api,
    apply_agent_result_to_session,
    agent_factory=None,
    handle_exception_cancel_fn=handle_exception_cancel,
    handle_exception_credential_self_heal_fn=handle_exception_credential_self_heal,
    exception_error_copy_fn=exception_error_copy,
    emit_and_persist_exception_streaming_error_fn=emit_and_persist_exception_streaming_error,
) -> StreamingExceptionHandlingResult:
    """Classify, optionally self-heal, and persist a streaming exception."""
    print('[webui] stream error:\n' + traceback.format_exc(), flush=True)
    err_str = sanitize_provider_error_text(str(exc))
    _exc_lower = err_str.lower()
    _classification = classify_provider_error(err_str, exc)
    if handle_exception_cancel_fn(
        cancel_event,
        session,
        stream_id,
        agent_lock,
        finalize_cancelled_turn,
        put_cancel,
        ephemeral=ephemeral,
        checkpoint_stop=checkpoint_stop,
        checkpoint_thread=checkpoint_thread,
        logger=logger,
    ):
        return StreamingExceptionHandlingResult(should_return=True)

    _exc_is_quota = _classification['type'] == 'quota_exhausted'
    # Exception quota text still includes: 'more credits' in _exc_lower, 'can only afford' in _exc_lower, 'fewer max_tokens' in _exc_lower.
    # Rate-limit detection remains guarded as: (not _exc_is_quota).
    _exc_is_rate_limit = (_classification['type'] == 'rate_limit') and (not _exc_is_quota)
    _exc_is_auth = _classification['type'] == 'auth_mismatch'  # detects '401' and 'unauthorized' via _classify_provider_error.
    _exc_is_not_found = _classification['type'] == 'model_not_found'  # detects '404', 'not found', 'does not exist', and 'invalid model'.
    _exc_is_cancelled = _classification['type'] == 'cancelled'
    _exc_is_interrupted = _classification['type'] == 'interrupted'
    _ = (_exc_lower, _exc_is_rate_limit, _exc_is_not_found, _exc_is_cancelled, _exc_is_interrupted)

    result = StreamingExceptionHandlingResult()
    if _exc_is_auth and not self_healed:
        exception_self_heal = handle_exception_credential_self_heal_fn(
            provider_id=runtime_vars.get('resolved_provider') or '',
            session_id=session_id,
            agent_lock=agent_lock,
            agent_factory=agent_factory,
            agent_kwargs=dict(runtime_vars.get('_agent_kwargs') or {}),
            agent_params=runtime_vars.get('_agent_params') or {},
            resolved_model=runtime_vars.get('resolved_model'),
            resolved_provider=runtime_vars.get('resolved_provider'),
            resolved_base_url=runtime_vars.get('resolved_base_url'),
            custom_provider_resolver=custom_provider_resolver,
            stream_id=stream_id,
            agent_instances=agent_instances,
            streams_lock=streams_lock,
            ephemeral=ephemeral,
            agent_sig=runtime_vars.get('_agent_sig'),
            user_message=runtime_vars.get('user_message'),
            system_message=runtime_vars.get('workspace_system_msg'),
            previous_messages=runtime_vars.get('_previous_messages') or [],
            previous_context_messages=runtime_vars.get('_previous_context_messages') or [],
            config=runtime_vars.get('_cfg') or {},
            persist_user_message=runtime_vars.get('msg_text') or '',
            sanitize_messages_for_api=sanitize_messages_for_api,
            output_bridge=runtime_vars.get('_output_bridge'),
            session=session,
            msg_text=runtime_vars.get('msg_text') or '',
            checkpoint_stop=checkpoint_stop,
            checkpoint_thread=checkpoint_thread,
            stop_checkpoint_thread=stop_checkpoint_thread,
            stream_writeback_is_current=stream_writeback_is_current,
            apply_agent_result_to_session=apply_agent_result_to_session,
            logger=logger,
        )
        if exception_self_heal.self_healed:
            result.self_healed = True
            result.runtime = exception_self_heal.runtime
            result.resolved_api_key = exception_self_heal.resolved_api_key
            result.resolved_provider = exception_self_heal.resolved_provider
            result.resolved_base_url = exception_self_heal.resolved_base_url
            result.agent_kwargs = exception_self_heal.agent_kwargs
        if exception_self_heal.should_return:
            result.should_return = True
            return result

    _exc_label, _exc_type, _exc_hint = exception_error_copy_fn(_classification)

    if not emit_and_persist_exception_streaming_error_fn(
        session,
        err_str=err_str,
        label=_exc_label,
        error_type=_exc_type,
        hint=_exc_hint,
        stream_id=stream_id,
        session_id=session_id,
        ephemeral=ephemeral,
        agent_lock=agent_lock,
        checkpoint_stop=checkpoint_stop,
        checkpoint_thread=checkpoint_thread,
        stop_checkpoint_thread=stop_checkpoint_thread,
        stream_writeback_is_current=stream_writeback_is_current,
        provider_error_payload=provider_error_payload,
        finalize_product_turn=finalize_product_turn,
        put=put,
        append_interrupted_turn_event=append_interrupted_turn_event,
        materialize_pending_user_turn=materialize_pending_user_turn,
        logger=logger,
    ):
        result.should_return = True
    return result
