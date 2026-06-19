"""Compatibility facade for WebUI process notification helpers."""

from __future__ import annotations

from api.streaming_process_notifications import (
    drain_webui_process_notifications,
    format_process_notification,
    mark_process_completion_consumed,
)


def format_process_notification_from_facade(evt: dict) -> str:
    return format_process_notification(evt)


def mark_process_completion_consumed_from_facade(process_registry, process_id: str) -> None:
    from api import streaming

    mark_process_completion_consumed(process_registry, process_id, logger=streaming.logger)


def drain_webui_process_notifications_from_facade(session_id: str) -> list[str]:
    from api import streaming

    return drain_webui_process_notifications(session_id, logger=streaming.logger)
