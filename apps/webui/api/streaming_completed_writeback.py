"""Completed-run writeback orchestration for WebUI streaming workers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from api.streaming_compression import apply_streaming_context_compression_side_effects
from api.streaming_context import apply_agent_result_to_session
from api.streaming_silent_failure import handle_silent_failure_after_merge
from api.streaming_tool_calls import strip_xml_tool_calls_from_assistant_messages
from api.streaming_turn_writeback import (
    apply_completed_turn_writeback_state,
    detect_silent_failure_after_merge,
    prepare_success_turn_writeback,
    save_completed_turn_and_journal,
)


@dataclass
class CompletedConversationWritebackResult:
    should_return: bool = False
    self_healed: bool = False
    completed_turn_state: Any = None
    result: dict[str, Any] | None = None
    agent: Any = None
    agent_kwargs: dict[str, Any] | None = None
    runtime: dict[str, Any] | None = None
    resolved_api_key: Any = None
    resolved_provider: str | None = None
    resolved_base_url: str | None = None


def handle_completed_conversation_writeback(
    result,
    *,
    session,
    agent,
    self_healed: bool,
    stream_id: str,
    session_id: str,
    cancel_event,
    agent_lock,
    ephemeral: bool,
    previous_messages,
    previous_context_messages,
    msg_text: str,
    output_bridge,
    live_tool_calls: list,
    turn_started_at,
    attachments,
    model: str,
    resolved_model: str | None,
    resolved_provider: str | None,
    resolved_base_url: str | None,
    resolved_profile_name: str | None,
    config: dict,
    pre_compression_count: int,
    usage_snapshot,
    agent_factory,
    agent_kwargs: dict[str, Any],
    agent_params,
    agent_sig: str | None,
    user_message,
    system_message,
    custom_provider_resolver,
    agent_instances,
    streams_lock,
    put,
    finalize_cancelled_turn: Callable[..., object],
    append_interrupted_turn_event: Callable[..., object],
    put_cancel: Callable[[], object],
    stream_writeback_is_current: Callable[[object, str], bool],
    classify_provider_error: Callable[..., dict],
    provider_error_payload: Callable[[str, str, str], dict],
    finalize_product_turn: Callable[..., object],
    materialize_pending_user_turn: Callable[[object], object] | None,
    sanitize_messages_for_api,
    has_new_assistant_reply,
    assistant_reply_added_after_current_turn,
    preserve_pre_compression_snapshot,
    compression_anchor_message_key,
    compact_summary_text,
    compression_summary_from_messages,
    title_from_fn,
    is_provisional_title,
    looks_invalid_generated_title,
    first_exchange_snippets,
    extract_gateway_routing_metadata,
    logger,
    prepare_success_turn_writeback_fn=prepare_success_turn_writeback,
    apply_agent_result_to_session_fn=apply_agent_result_to_session,
    detect_silent_failure_after_merge_fn=detect_silent_failure_after_merge,
    handle_silent_failure_after_merge_fn=handle_silent_failure_after_merge,
    apply_streaming_context_compression_side_effects_fn=apply_streaming_context_compression_side_effects,
    apply_completed_turn_writeback_state_fn=apply_completed_turn_writeback_state,
    save_completed_turn_and_journal_fn=save_completed_turn_and_journal,
    strip_xml_tool_calls_fn=strip_xml_tool_calls_from_assistant_messages,
) -> CompletedConversationWritebackResult:
    """Merge a completed non-ephemeral result into the session and save it."""
    with agent_lock:
        if not prepare_success_turn_writeback_fn(
            session,
            stream_id=stream_id,
            ephemeral=ephemeral,
            stream_writeback_is_current=stream_writeback_is_current,
            cancel_event=cancel_event,
            finalize_cancelled_turn=finalize_cancelled_turn,
            put_cancel=put_cancel,
            logger=logger,
        ):
            return CompletedConversationWritebackResult(should_return=True)

        apply_agent_result_to_session_fn(
            session,
            previous_messages,
            previous_context_messages,
            result.get('messages'),
            msg_text,
            strip_xml_tool_calls_fn=strip_xml_tool_calls_fn,
        )

        silent_failure = detect_silent_failure_after_merge_fn(
            result,
            previous_context_messages,
            msg_text=msg_text,
            token_sent=output_bridge.token_sent,
            assistant_reply_added_after_current_turn=assistant_reply_added_after_current_turn,
        )
        silent_result = handle_silent_failure_after_merge_fn(
            silent_failure,
            agent=agent,
            result=result,
            self_healed=self_healed,
            session=session,
            stream_id=stream_id,
            cancel_event=cancel_event,
            finalize_cancelled_turn=finalize_cancelled_turn,
            append_interrupted_turn_event=append_interrupted_turn_event,
            put_cancel=put_cancel,
            ephemeral=ephemeral,
            classify_provider_error=classify_provider_error,
            provider_error_payload=provider_error_payload,
            finalize_product_turn=finalize_product_turn,
            materialize_pending_user_turn=materialize_pending_user_turn,
            put=put,
            provider_id=resolved_provider or '',
            session_id=session_id,
            agent_lock=agent_lock,
            agent_factory=agent_factory,
            agent_kwargs=agent_kwargs,
            agent_params=agent_params,
            resolved_model=resolved_model,
            resolved_provider=resolved_provider,
            resolved_base_url=resolved_base_url,
            custom_provider_resolver=custom_provider_resolver,
            agent_instances=agent_instances,
            streams_lock=streams_lock,
            agent_sig=agent_sig,
            user_message=user_message,
            system_message=system_message,
            previous_messages=previous_messages,
            previous_context_messages=previous_context_messages,
            config=config,
            persist_user_message=msg_text,
            sanitize_messages_for_api=sanitize_messages_for_api,
            output_bridge=output_bridge,
            msg_text=msg_text,
            has_new_assistant_reply=has_new_assistant_reply,
            apply_agent_result_to_session=apply_agent_result_to_session_fn,
            logger=logger,
        )
        if silent_result.self_healed:
            result = silent_result.result if silent_result.result is not None else result
            agent = silent_result.agent
            agent_kwargs = silent_result.agent_kwargs
            resolved_provider = silent_result.resolved_provider
            resolved_base_url = silent_result.resolved_base_url
        # Legacy #373 source tests and clients look for the no_response type.
        # The silent-failure helper preserves that type while this branch
        # prevents the worker from also emitting a terminal done payload.
        if silent_result.should_return:
            return CompletedConversationWritebackResult(
                should_return=True,
                self_healed=silent_result.self_healed,
                result=result,
                agent=agent,
                agent_kwargs=agent_kwargs,
                runtime=silent_result.runtime,
                resolved_api_key=silent_result.resolved_api_key,
                resolved_provider=resolved_provider,
                resolved_base_url=resolved_base_url,
            )  # apperror already closes the stream on the client side

        apply_streaming_context_compression_side_effects_fn(
            session,
            agent,
            original_session_id=session_id,
            resolved_profile_name=resolved_profile_name,
            agent_lock=agent_lock,
            pre_compression_count=pre_compression_count,
            preserve_pre_compression_snapshot=preserve_pre_compression_snapshot,
            compression_anchor_message_key=compression_anchor_message_key,
            compact_summary_text=compact_summary_text,
            compression_summary_from_messages=compression_summary_from_messages,
            put=put,
            usage_snapshot=usage_snapshot,
            logger=logger,
        )

        completed_turn_state = apply_completed_turn_writeback_state_fn(
            session,
            agent,
            result,
            msg_text=msg_text,
            attachments=attachments,
            live_tool_calls=live_tool_calls,
            reasoning_text=output_bridge.reasoning_text,
            turn_started_at=turn_started_at,
            requested_model=resolved_model or model,
            requested_provider=resolved_provider or '',
            config=config,
            title_from_fn=title_from_fn,
            is_provisional_title=is_provisional_title,
            looks_invalid_generated_title=looks_invalid_generated_title,
            first_exchange_snippets=first_exchange_snippets,
            extract_gateway_routing_metadata=extract_gateway_routing_metadata,
        )
        if not save_completed_turn_and_journal_fn(
            session,
            agent,
            stream_id=stream_id,
            cancel_event=cancel_event,
            finalize_cancelled_turn=finalize_cancelled_turn,
            put_cancel=put_cancel,
            logger=logger,
        ):
            return CompletedConversationWritebackResult(
                should_return=True,
                self_healed=silent_result.self_healed,
                completed_turn_state=completed_turn_state,
                result=result,
                agent=agent,
                agent_kwargs=agent_kwargs,
                runtime=silent_result.runtime,
                resolved_api_key=silent_result.resolved_api_key,
                resolved_provider=resolved_provider,
                resolved_base_url=resolved_base_url,
            )

    return CompletedConversationWritebackResult(
        self_healed=silent_result.self_healed,
        completed_turn_state=completed_turn_state,
        result=result,
        agent=agent,
        agent_kwargs=agent_kwargs,
        runtime=silent_result.runtime,
        resolved_api_key=silent_result.resolved_api_key,
        resolved_provider=resolved_provider,
        resolved_base_url=resolved_base_url,
    )
