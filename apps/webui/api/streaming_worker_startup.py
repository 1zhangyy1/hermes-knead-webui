"""Startup orchestration for WebUI streaming worker turns."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from api.streaming_gateway_notifications import register_streaming_gateway_notifications
from api.streaming_runtime_helpers import (
    activate_streaming_profile_runtime,
    restore_agent_process_env,
)


@dataclass
class StreamingWorkerStartupResult:
    should_return: bool = False
    session: Any = None
    agent_lock: Any = None
    provider_context: str | None = None
    profile_home: str | None = None
    resolved_profile_name: str | None = None
    profile_env_snapshot: dict | None = None
    runtime_env_snapshot: dict | None = None
    gateway_notifications: Any = None


def prepare_streaming_worker_startup(
    *,
    session_id: str,
    stream_id: str,
    workspace,
    model: str,
    model_provider: str | None,
    ephemeral: bool,
    cancel_event,
    put,
    get_session: Callable[[str], Any],
    update_active_run: Callable[..., object],
    get_session_agent_lock: Callable[[str], Any],
    handle_preflight_cancel: Callable[..., bool],
    finalize_cancelled_turn: Callable[..., object],
    put_cancel: Callable[[], object],
    set_thread_env: Callable[..., object],
    env_lock,
    logger,
    activate_streaming_profile_runtime_fn=activate_streaming_profile_runtime,
    register_streaming_gateway_notifications_fn=register_streaming_gateway_notifications,
    restore_agent_process_env_fn=restore_agent_process_env,
) -> StreamingWorkerStartupResult:
    """Prepare the session, profile runtime, and gateway callbacks for a run."""
    session = get_session(session_id)
    update_active_run(stream_id, phase="running", session_id=session_id)
    session.workspace = str(Path(workspace).expanduser().resolve())
    session.model = model
    provider_context = (
        str(model_provider).strip().lower()
        if model_provider is not None
        else getattr(session, "model_provider", None)
    )
    session.model_provider = provider_context or None

    agent_lock = get_session_agent_lock(session_id)
    if handle_preflight_cancel(
        cancel_event,
        session,
        agent_lock,
        finalize_cancelled_turn,
        put_cancel,
        ephemeral=ephemeral,
    ):
        return StreamingWorkerStartupResult(
            should_return=True,
            session=session,
            agent_lock=agent_lock,
            provider_context=provider_context,
        )

    activation = None
    try:
        activation = activate_streaming_profile_runtime_fn(
            session,
            workspace=str(session.workspace),
            session_id=session_id,
            set_thread_env=set_thread_env,
            env_lock=env_lock,
        )
        gateway_notifications = register_streaming_gateway_notifications_fn(
            session_id,
            put=put,
            logger=logger,
        )
    except Exception:
        if activation is not None:
            restore_agent_process_env_fn(
                activation.profile_env_snapshot,
                activation.runtime_env_snapshot,
                env_lock=env_lock,
            )
        raise

    return StreamingWorkerStartupResult(
        session=session,
        agent_lock=agent_lock,
        provider_context=provider_context,
        profile_home=activation.profile_home,
        resolved_profile_name=activation.resolved_profile_name,
        profile_env_snapshot=activation.profile_env_snapshot,
        runtime_env_snapshot=activation.runtime_env_snapshot,
        gateway_notifications=gateway_notifications,
    )
