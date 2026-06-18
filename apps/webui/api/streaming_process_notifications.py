"""Background process completion notifications for WebUI streaming."""

from __future__ import annotations

import queue


def format_process_notification(evt: dict) -> str:
    """Format a completed background process notification for agent input."""
    if not isinstance(evt, dict):
        return ''
    if evt.get('type') != 'completion':
        return ''
    _sid = evt.get('session_id', '')
    _cmd = evt.get('command', '')
    _exit = evt.get('exit_code', '')
    _out = evt.get('output') or ''
    if len(_out) > 4000:
        _out = _out[:4000] + '\n... (truncated)'
    return (
        f"[IMPORTANT: Background process {_sid} completed (exit code {_exit}).\n"
        f"Command: {_cmd}\n"
        f"Output:\n{_out}]"
    )


def mark_process_completion_consumed(process_registry, process_id: str, *, logger=None) -> None:
    """Best-effort bridge to the agent registry's private completion marker."""
    try:
        with process_registry._lock:
            process_registry._completion_consumed.add(process_id)
    except Exception:
        if logger is not None:
            logger.debug("Failed to mark process completion consumed", exc_info=True)


def drain_webui_process_notifications(session_id: str, *, process_registry=None, logger=None) -> list[str]:
    """Return completion notifications that belong to this WebUI session.

    The agent registry completion queue is process-wide and events do not carry
    the WebUI session key directly. Look up the live process session before
    delivery so completions from other tabs remain queued for their owners.
    """
    if not session_id:
        return []
    if process_registry is None:
        try:
            from tools.process_registry import process_registry as _process_registry
        except Exception:
            return []
        process_registry = _process_registry

    notifications: list[str] = []
    skipped_events: list[dict] = []
    completion_queue = getattr(process_registry, 'completion_queue', None)
    if completion_queue is None:
        return []

    while True:
        try:
            evt = completion_queue.get_nowait()
        except queue.Empty:
            break
        except Exception:
            if logger is not None:
                logger.debug("Failed to drain process completion queue", exc_info=True)
            break

        evt_sid = str(evt.get('session_id') or '') if isinstance(evt, dict) else ''
        if not evt_sid:
            skipped_events.append(evt)
            continue
        try:
            if process_registry.is_completion_consumed(evt_sid):
                continue
            proc = process_registry.get(evt_sid)
        except Exception:
            proc = None
        if getattr(proc, 'session_key', None) != session_id:
            skipped_events.append(evt)
            continue

        notification = format_process_notification(evt)
        if notification:
            notifications.append(notification)
            mark_process_completion_consumed(process_registry, evt_sid, logger=logger)

    for evt in skipped_events:
        try:
            completion_queue.put(evt)
        except Exception:
            if logger is not None:
                logger.debug("Failed to requeue process completion event", exc_info=True)
            break
    return notifications


def message_text_with_process_notifications(msg_text: str, process_notifications: list[str] | None) -> str:
    """Prefix drained process notifications without changing persisted user text."""
    if process_notifications:
        return "\n\n".join([*process_notifications, msg_text]).strip()
    return msg_text
