"""Facade wiring from the legacy streaming module into exception handling."""

from __future__ import annotations

from typing import Any

from api.streaming_exception_handling import handle_streaming_exception


def handle_streaming_exception_from_facade(
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
    finalize_product_turn,
    put_cancel,
    put,
):
    """Handle a worker exception using callbacks exposed by ``api.streaming``."""
    from api import streaming as streaming_api

    return handle_streaming_exception(
        exc,
        runtime_vars=runtime_vars,
        self_healed=self_healed,
        session=session,
        stream_id=stream_id,
        session_id=session_id,
        cancel_event=cancel_event,
        agent_lock=agent_lock,
        checkpoint_stop=checkpoint_stop,
        checkpoint_thread=checkpoint_thread,
        ephemeral=ephemeral,
        logger=streaming_api.logger,
        sanitize_provider_error_text=streaming_api._sanitize_provider_error_text,
        classify_provider_error=streaming_api._classify_provider_error,
        finalize_cancelled_turn=streaming_api._finalize_cancelled_turn,
        put_cancel=put_cancel,
        provider_error_payload=streaming_api._provider_error_payload,
        finalize_product_turn=finalize_product_turn,
        put=put,
        append_interrupted_turn_event=streaming_api._append_interrupted_turn_event,
        materialize_pending_user_turn=streaming_api._materialize_pending_user_turn_before_error,
        stop_checkpoint_thread=streaming_api._stop_checkpoint_thread,
        stream_writeback_is_current=streaming_api._stream_writeback_is_current,
        custom_provider_resolver=streaming_api.resolve_custom_provider_connection,
        agent_instances=streaming_api.AGENT_INSTANCES,
        streams_lock=streaming_api.STREAMS_LOCK,
        sanitize_messages_for_api=streaming_api._sanitize_messages_for_api,
        apply_agent_result_to_session=streaming_api._apply_agent_result_to_session,
        agent_factory=runtime_vars.get('_AIAgent'),
    )
