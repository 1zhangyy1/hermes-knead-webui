"""Conversation execution helpers for WebUI streaming workers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from api.streaming_ephemeral import handle_completed_conversation_post_run


@dataclass(frozen=True)
class ConversationRunResult:
    result: dict[str, Any] | None
    should_return: bool = False


def run_agent_conversation_and_handle_post_run(
    *,
    agent,
    user_message,
    system_message,
    previous_context_messages,
    config: dict,
    session,
    session_id: str,
    stream_id: str,
    cancel_event,
    agent_lock,
    finalize_cancelled_turn,
    put_cancel,
    ephemeral: bool,
    checkpoint_stop,
    checkpoint_thread,
    put,
    msg_text: str,
    sanitize_messages_for_api: Callable[..., list],
    handle_post_run_cancel,
    stop_checkpoint_thread,
    logger,
    handle_completed_conversation_post_run_fn=handle_completed_conversation_post_run,
) -> ConversationRunResult:
    """Run the agent and process post-run cancel/ephemeral/checkpoint gates."""
    result = agent.run_conversation(
        user_message=user_message,
        system_message=system_message,
        conversation_history=sanitize_messages_for_api(previous_context_messages, cfg=config),
        task_id=session_id,
        persist_user_message=msg_text,
    )
    if handle_completed_conversation_post_run_fn(
        result,
        session=session,
        session_id=session_id,
        stream_id=stream_id,
        cancel_event=cancel_event,
        agent_lock=agent_lock,
        finalize_cancelled_turn=finalize_cancelled_turn,
        put_cancel=put_cancel,
        ephemeral=ephemeral,
        checkpoint_stop=checkpoint_stop,
        checkpoint_thread=checkpoint_thread,
        put=put,
        handle_post_run_cancel=handle_post_run_cancel,
        stop_checkpoint_thread_fn=stop_checkpoint_thread,
        logger=logger,
    ):
        return ConversationRunResult(result=result, should_return=True)
    return ConversationRunResult(result=result)
