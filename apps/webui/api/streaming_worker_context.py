"""Initial worker context setup for WebUI streaming runs."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from api.config import register_active_run
from api.run_journal import RunJournalWriter
from api.streaming_product_turn import ProductTurnFinalizer
from api.streaming_run_state import initialize_webui_streaming_run_state
from api.streaming_turn_journal import append_worker_started_turn_event


@dataclass(frozen=True)
class StreamingWorkerContext:
    should_return: bool = False
    run_state: Any = None
    cancel_event: Any = None
    put: Callable[..., object] | None = None
    finalize_product_turn: Callable[..., object] | None = None
    put_cancel: Callable[..., object] | None = None


def initialize_streaming_worker_context(
    *,
    stream_id: str,
    session_id: str,
    workspace,
    model,
    model_provider,
    ephemeral: bool,
    product_context,
    streams: dict,
    get_session: Callable[[], object | None],
    get_agent: Callable[[], object | None],
    logger,
    register_active_run_fn=register_active_run,
    run_journal_factory=RunJournalWriter,
    product_turn_finalizer_factory=ProductTurnFinalizer,
    append_worker_started_turn_event_fn=append_worker_started_turn_event,
    initialize_run_state_fn=initialize_webui_streaming_run_state,
    time_fn=time.time,
) -> StreamingWorkerContext:
    """Register a stream and build the callbacks used by the worker body."""
    q = streams.get(stream_id)
    if q is None:
        return StreamingWorkerContext(should_return=True)

    register_active_run_fn(
        stream_id,
        session_id=session_id,
        started_at=time_fn(),
        phase="starting",
        workspace=str(workspace),
        model=model,
        provider=model_provider,
        ephemeral=bool(ephemeral),
    )
    product_turn_finalizer = product_turn_finalizer_factory(product_context, logger=logger)

    try:
        run_journal = run_journal_factory(session_id, stream_id)
    except Exception:
        run_journal = None
        logger.debug("Failed to initialize run journal for stream %s", stream_id, exc_info=True)
    if not ephemeral:
        append_worker_started_turn_event_fn(session_id, stream_id, logger=logger)

    run_state = initialize_run_state_fn(
        stream_id=stream_id,
        session_id=session_id,
        queue=q,
        run_journal=run_journal,
        get_session=get_session,
        get_agent=get_agent,
        logger=logger,
    )
    put = run_state.put

    def finalize_product_turn(
        *,
        failed: bool = False,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        product_turn_finalizer.finalize(
            failed=failed,
            error_type=error_type,
            error_message=error_message,
        )

    def put_cancel(message: str = "Cancelled by user") -> None:
        finalize_product_turn(failed=True)
        put('cancel', {'message': message})

    return StreamingWorkerContext(
        run_state=run_state,
        cancel_event=run_state.cancel_event,
        put=put,
        finalize_product_turn=finalize_product_turn,
        put_cancel=put_cancel,
    )
