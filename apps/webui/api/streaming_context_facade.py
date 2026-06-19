"""Compatibility facade for WebUI streaming context helpers."""

from __future__ import annotations

from api.streaming_context import preserve_pre_compression_snapshot


def preserve_pre_compression_snapshot_from_facade(session, old_sid: str) -> None:
    from api import streaming

    return preserve_pre_compression_snapshot(
        session,
        old_sid,
        session_dir=streaming.SESSION_DIR,
        logger=streaming.logger,
    )


def stream_writeback_is_current_from_facade(session, stream_id) -> bool:
    """Return True only while a worker still owns the session writeback."""
    return bool(stream_id) and getattr(session, "active_stream_id", None) == stream_id
