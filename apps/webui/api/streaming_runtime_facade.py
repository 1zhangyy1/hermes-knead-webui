"""Compatibility facade for WebUI streaming runtime helpers."""

from __future__ import annotations

from api.streaming_runtime_helpers import clarify_timeout_seconds


def clarify_timeout_seconds_from_facade(default: int = 120) -> int:
    from api import streaming

    return clarify_timeout_seconds(streaming.get_config, default)
