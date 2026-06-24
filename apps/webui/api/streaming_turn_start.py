"""Prepare a WebUI streaming turn before calling the agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from api.streaming_attachments import build_native_multimodal_message
from api.streaming_checkpoint import start_periodic_checkpoint
from api.streaming_context import TurnStartSnapshot, capture_turn_start_snapshot
from api.streaming_process_notifications import (
    drain_webui_process_notifications,
    message_text_with_process_notifications,
)
from api.streaming_runtime_prompt import (
    build_workspace_system_message,
    configure_agent_runtime_prompt,
)
from api.streaming_titles import workspace_context_prefix


@dataclass
class StreamingTurnInput:
    user_message: Any
    system_message: str
    turn_start: TurnStartSnapshot
    checkpoint_runner: Any


def prepare_streaming_turn_input(
    *,
    session,
    agent,
    msg_text: str,
    attachments,
    workspace,
    config: dict,
    product_context,
    agent_lock,
    checkpoint_activity,
    session_id: str,
    personality_name,
    webui_ephemeral_system_prompt: Callable,
    logger,
    agent_instruction: str | None = None,
    workspace_context_prefix_fn=workspace_context_prefix,
    build_workspace_system_message_fn=build_workspace_system_message,
    configure_agent_runtime_prompt_fn=configure_agent_runtime_prompt,
    capture_turn_start_snapshot_fn=capture_turn_start_snapshot,
    start_periodic_checkpoint_fn=start_periodic_checkpoint,
    drain_process_notifications_fn=drain_webui_process_notifications,
    message_text_with_process_notifications_fn=message_text_with_process_notifications,
    build_native_multimodal_message_fn=build_native_multimodal_message,
) -> StreamingTurnInput:
    """Prepare prompt, turn snapshot, checkpointing, and the agent input payload."""
    workspace_ctx = workspace_context_prefix_fn(str(session.workspace))
    system_message = build_workspace_system_message_fn(session.workspace)
    configure_agent_runtime_prompt_fn(
        agent,
        config=config,
        personality_name=personality_name,
        product_context=product_context,
        agent_instruction=agent_instruction,
        webui_ephemeral_system_prompt=webui_ephemeral_system_prompt,
        logger=logger,
    )
    turn_start = capture_turn_start_snapshot_fn(session, agent, msg_text)

    # Persist the user message before streaming starts so it is durable even if
    # the server crashes before the first checkpoint fires.
    with agent_lock:
        session.save(touch_updated_at=True, skip_index=False)

    checkpoint_runner = start_periodic_checkpoint_fn(
        session,
        agent_lock=agent_lock,
        checkpoint_activity=checkpoint_activity,
        session_id=session_id,
        logger=logger,
    )
    try:
        process_notifications = drain_process_notifications_fn(session_id, logger=logger)
        agent_msg_text = message_text_with_process_notifications_fn(msg_text, process_notifications)
        user_message = build_native_multimodal_message_fn(
            workspace_ctx,
            agent_msg_text,
            attachments,
            workspace,
            cfg=config,
        )
    except Exception:
        try:
            checkpoint_runner.stop_and_join()
        except Exception:
            if logger is not None:
                logger.debug("Failed to stop checkpoint after turn input preparation error", exc_info=True)
        raise

    return StreamingTurnInput(
        user_message=user_message,
        system_message=system_message,
        turn_start=turn_start,
        checkpoint_runner=checkpoint_runner,
    )
