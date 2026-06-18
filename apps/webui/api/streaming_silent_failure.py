"""Silent-failure orchestration for WebUI streaming workers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from api.streaming_error_writeback import (
    classify_silent_failure_error,
    emit_and_persist_silent_failure_error,
)
from api.streaming_recovery import handle_silent_failure_credential_self_heal


@dataclass
class SilentFailureHandlingResult:
    should_return: bool = False
    assistant_added: bool = False
    self_healed: bool = False
    self_heal_succeeded: bool = False
    result: dict[str, Any] | None = None
    agent: Any = None
    agent_kwargs: dict[str, Any] | None = None
    runtime: dict[str, Any] | None = None
    resolved_api_key: Any = None
    resolved_provider: str | None = None
    resolved_base_url: str | None = None


def handle_silent_failure_after_merge(
    silent_failure,
    *,
    agent,
    result,
    self_healed: bool,
    session,
    stream_id: str,
    cancel_event,
    finalize_cancelled_turn: Callable[..., object],
    append_interrupted_turn_event: Callable[..., object],
    put_cancel: Callable[[], object],
    ephemeral: bool,
    classify_provider_error: Callable[..., dict],
    provider_error_payload: Callable[[str, str, str], dict],
    finalize_product_turn: Callable[..., object],
    materialize_pending_user_turn: Callable[[object], object] | None,
    put: Callable[[str, object], object],
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
    agent_instances,
    streams_lock,
    agent_sig: str | None,
    user_message,
    system_message,
    previous_messages,
    previous_context_messages,
    config,
    persist_user_message: str,
    sanitize_messages_for_api,
    output_bridge,
    msg_text: str,
    has_new_assistant_reply,
    apply_agent_result_to_session,
    logger,
    classify_silent_failure_error_fn=classify_silent_failure_error,
    handle_silent_failure_credential_self_heal_fn=handle_silent_failure_credential_self_heal,
    emit_and_persist_silent_failure_error_fn=emit_and_persist_silent_failure_error,
) -> SilentFailureHandlingResult:
    """Handle a completed run that produced no assistant message or tokens.

    This function runs inside the caller's success-path session lock. It must
    not reacquire that lock; credential self-heal receives the lock only as a
    compatibility argument for lower-level helpers.
    """
    assistant_added = bool(getattr(silent_failure, 'assistant_added', False))
    if not getattr(silent_failure, 'should_handle', False):
        return SilentFailureHandlingResult(assistant_added=assistant_added)

    if cancel_event.is_set():
        finalize_cancelled_turn(session, ephemeral=ephemeral)
        if not ephemeral:
            append_interrupted_turn_event(session.session_id, stream_id, logger=logger)
        put_cancel()
        return SilentFailureHandlingResult(
            should_return=True,
            assistant_added=assistant_added,
        )

    silent_error = classify_silent_failure_error_fn(
        agent,
        result,
        classify_provider_error=classify_provider_error,
    )

    if silent_error.is_auth and not self_healed:
        silent_self_heal = handle_silent_failure_credential_self_heal_fn(
            should_attempt=True,
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
            previous_messages=previous_messages,
            previous_context_messages=previous_context_messages,
            config=config,
            persist_user_message=persist_user_message,
            sanitize_messages_for_api=sanitize_messages_for_api,
            output_bridge=output_bridge,
            prev_len=getattr(silent_failure, 'previous_context_count', 0),
            session=session,
            msg_text=msg_text,
            has_new_assistant_reply=has_new_assistant_reply,
            apply_agent_result_to_session=apply_agent_result_to_session,
            logger=logger,
        )
        if silent_self_heal.self_healed:
            if silent_self_heal.succeeded and silent_self_heal.result is not None:
                return SilentFailureHandlingResult(
                    assistant_added=True,
                    self_healed=True,
                    self_heal_succeeded=True,
                    result=silent_self_heal.result,
                    agent=silent_self_heal.agent,
                    agent_kwargs=silent_self_heal.agent_kwargs,
                    runtime=silent_self_heal.runtime,
                    resolved_api_key=silent_self_heal.resolved_api_key,
                    resolved_provider=silent_self_heal.resolved_provider,
                    resolved_base_url=silent_self_heal.resolved_base_url,
                )
            return SilentFailureHandlingResult(
                assistant_added=assistant_added,
                self_healed=True,
                result=silent_self_heal.result,
                agent=silent_self_heal.agent,
                agent_kwargs=silent_self_heal.agent_kwargs,
                runtime=silent_self_heal.runtime,
                resolved_api_key=silent_self_heal.resolved_api_key,
                resolved_provider=silent_self_heal.resolved_provider,
                resolved_base_url=silent_self_heal.resolved_base_url,
            )

    emit_and_persist_silent_failure_error_fn(
        session,
        silent_error,
        put=put,
        provider_error_payload=provider_error_payload,
        finalize_product_turn=finalize_product_turn,
        materialize_pending_user_turn=materialize_pending_user_turn,
        logger=logger,
    )
    return SilentFailureHandlingResult(
        should_return=True,
        assistant_added=assistant_added,
    )
