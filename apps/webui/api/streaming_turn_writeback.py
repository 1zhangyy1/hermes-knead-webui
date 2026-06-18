"""Successful-turn session writeback helpers for WebUI streaming workers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from api.streaming_attachments import tag_matching_user_message_attachments
from api.streaming_context_window import persist_context_window_on_session
from api.streaming_memory_lifecycle import mark_completed_turn_memory_lifecycle
from api.streaming_title_writeback import prepare_completed_turn_title
from api.streaming_tool_calls import extract_tool_calls_from_messages
from api.streaming_turn_journal import (
    append_assistant_started_turn_event,
    append_completed_turn_event,
    append_interrupted_turn_event,
)
from api.streaming_turn_metadata import (
    apply_completed_turn_metadata,
    attach_reasoning_trace_to_last_assistant,
)
from api.streaming_usage import apply_agent_token_usage_to_session


@dataclass(frozen=True)
class CompletedTurnWritebackState:
    title_plan: Any
    token_usage: Any
    tool_calls: list
    turn_metadata: Any


@dataclass(frozen=True)
class SilentFailureDetectionState:
    previous_context_count: int
    assistant_added: bool
    token_sent: bool
    should_handle: bool


def detect_silent_failure_after_merge(
    result,
    previous_context_messages,
    *,
    msg_text: str,
    token_sent: bool,
    assistant_reply_added_after_current_turn: Callable,
) -> SilentFailureDetectionState:
    """Detect whether a completed run produced no current-turn assistant reply."""
    result_messages = (result or {}).get('messages') or []
    previous_context_count = len(previous_context_messages or [])
    assistant_added = assistant_reply_added_after_current_turn(
        result_messages,
        previous_context_messages,
        msg_text,
    )
    return SilentFailureDetectionState(
        previous_context_count=previous_context_count,
        assistant_added=assistant_added,
        token_sent=bool(token_sent),
        should_handle=(not assistant_added and not token_sent),
    )


def apply_completed_turn_writeback_state(
    session,
    agent,
    result,
    *,
    msg_text: str,
    attachments,
    live_tool_calls: list,
    reasoning_text: str,
    turn_started_at,
    requested_model: str,
    requested_provider: str,
    config: dict,
    title_from_fn: Callable,
    is_provisional_title: Callable,
    looks_invalid_generated_title: Callable,
    first_exchange_snippets: Callable,
    extract_gateway_routing_metadata: Callable,
) -> CompletedTurnWritebackState:
    """Apply successful-turn session mutations that must happen before save."""
    title_plan = prepare_completed_turn_title(
        session,
        title_from_fn=title_from_fn,
        is_provisional_title=is_provisional_title,
        looks_invalid_generated_title=looks_invalid_generated_title,
        first_exchange_snippets=first_exchange_snippets,
    )
    token_usage = apply_agent_token_usage_to_session(session, agent)
    output_tokens = token_usage.output_tokens
    tool_calls = extract_tool_calls_from_messages(
        session.messages,
        live_tool_calls=live_tool_calls,
    )
    session.tool_calls = tool_calls
    session.active_stream_id = None
    session.pending_user_message = None
    session.pending_attachments = []
    session.pending_started_at = None
    tag_matching_user_message_attachments(session.messages, msg_text, attachments)
    # Persist reasoning trace in the session so it survives reload.
    # Must run BEFORE session.save() — otherwise the mutation lives only in
    # memory until the next turn's save, and the last-turn thinking card
    # is lost when the user reloads immediately after a response.
    attach_reasoning_trace_to_last_assistant(session.messages, reasoning_text)
    turn_metadata = apply_completed_turn_metadata(
        session,
        agent,
        result,
        turn_started_at=turn_started_at,
        output_tokens=output_tokens,
        requested_model=requested_model,
        requested_provider=requested_provider,
        extract_gateway_routing_metadata=extract_gateway_routing_metadata,
    )
    persist_context_window_on_session(
        session,
        agent,
        config,
        resolved_model=requested_model,
        resolved_provider=requested_provider,
    )
    return CompletedTurnWritebackState(
        title_plan=title_plan,
        token_usage=token_usage,
        tool_calls=tool_calls,
        turn_metadata=turn_metadata,
    )


def prepare_success_turn_writeback(
    session,
    *,
    stream_id: str,
    ephemeral: bool,
    stream_writeback_is_current: Callable[[object, str], bool],
    cancel_event,
    finalize_cancelled_turn: Callable,
    put_cancel: Callable[[], None],
    logger=None,
) -> bool:
    """Guard successful result writeback before mutating the session transcript."""
    if not ephemeral and not stream_writeback_is_current(session, stream_id):
        if logger is not None:
            logger.info(
                "Skipping stale stream writeback for session %s stream %s; active_stream_id=%s",
                getattr(session, 'session_id', None),
                stream_id,
                getattr(session, 'active_stream_id', None),
            )
        return False
    if cancel_event.is_set():
        finalize_cancelled_turn(session, ephemeral=False)
        append_interrupted_turn_event(session.session_id, stream_id, logger=logger)
        put_cancel()
        return False
    return True


def save_completed_turn_and_journal(
    session,
    agent,
    *,
    stream_id: str,
    cancel_event,
    finalize_cancelled_turn: Callable,
    put_cancel: Callable[[], None],
    logger=None,
) -> bool:
    """Persist a completed non-ephemeral turn and append lifecycle journal events."""
    if session.messages:
        append_assistant_started_turn_event(
            session.session_id,
            stream_id,
            session.messages,
            logger=logger,
        )
    if cancel_event.is_set():
        finalize_cancelled_turn(session, ephemeral=False)
        append_interrupted_turn_event(session.session_id, stream_id, logger=logger)
        put_cancel()
        return False
    session.save()
    if cancel_event.is_set():
        finalize_cancelled_turn(session, ephemeral=False)
        append_interrupted_turn_event(session.session_id, stream_id, logger=logger)
        put_cancel()
        return False

    append_completed_turn_event(session.session_id, stream_id, session.messages, logger=logger)
    # Keep this marker inside the caller's per-session writeback lock so
    # completed-turn ordering stays aligned with session save/journal.
    mark_completed_turn_memory_lifecycle(session.session_id, agent, logger=logger)
    return True
