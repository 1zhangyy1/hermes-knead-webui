"""Compatibility facade for WebUI chat steer helpers."""

from __future__ import annotations

from api.streaming_chat_steer import handle_chat_steer


def handle_chat_steer_from_facade(handler, body: dict) -> bool:
    from api import streaming

    return handle_chat_steer(
        handler,
        body,
        get_session=streaming.get_session,
        logger=streaming.logger,
    )
