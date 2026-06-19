"""Small state helpers for the WebUI streaming worker."""

from __future__ import annotations

from typing import Any, Mapping


def current_checkpoint_handles(
    checkpoint_state: Mapping[str, Any] | None,
    checkpoint_stop,
    checkpoint_thread,
):
    """Return the latest checkpoint stop/thread handles."""
    checkpoint_state = checkpoint_state or {}
    return (
        checkpoint_state.get('stop') or checkpoint_stop,
        checkpoint_state.get('thread') or checkpoint_thread,
    )


def exception_runtime_vars(
    worker_locals: Mapping[str, Any],
    setup_runtime_vars: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Merge worker locals with setup/runtime values for exception recovery."""
    runtime_vars = dict(worker_locals)
    runtime_vars.update(setup_runtime_vars or {})
    return runtime_vars
