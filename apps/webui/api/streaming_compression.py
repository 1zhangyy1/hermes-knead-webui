"""Context compression side effects for WebUI streaming turns."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CompressionSideEffectResult:
    compressed: bool
    old_session_id: str | None = None
    new_session_id: str | None = None


def handle_context_compression_side_effects(
    session,
    agent,
    *,
    original_session_id: str,
    resolved_profile_name,
    agent_lock,
    pre_compression_count: int,
    preserve_pre_compression_snapshot,
    sessions_lock,
    sessions,
    session_agent_locks,
    session_agent_locks_lock,
    session_agent_cache,
    session_agent_cache_lock,
    visible_messages_for_anchor,
    compression_anchor_message_key,
    compact_summary_text,
    compression_summary_from_messages,
    put,
    usage_snapshot,
    logger=None,
) -> CompressionSideEffectResult:
    """Apply session/cache/anchor updates after context compression."""
    agent_session_id = getattr(agent, 'session_id', None)
    compressed = False
    old_session_id = None
    new_session_id = None

    if agent_session_id and agent_session_id != original_session_id:
        old_session_id = original_session_id
        new_session_id = agent_session_id
        session.session_id = new_session_id

        if not getattr(session, 'profile', None) and resolved_profile_name:
            session.profile = resolved_profile_name
            if logger is not None:
                logger.info(
                    "Stamped profile=%r on continuation session %s after compression",
                    resolved_profile_name,
                    new_session_id,
                )

        preserve_pre_compression_snapshot(session, old_session_id)
        session.parent_session_id = old_session_id

        with sessions_lock:
            if old_session_id in sessions:
                sessions[new_session_id] = sessions.pop(old_session_id)

        with session_agent_locks_lock:
            session_agent_locks[new_session_id] = agent_lock
            session_agent_locks.pop(old_session_id, None)

        with session_agent_cache_lock:
            cached_entry = session_agent_cache.pop(old_session_id, None)
            if cached_entry:
                session_agent_cache[new_session_id] = cached_entry

        compressed = True

    if not compressed:
        compressor = getattr(agent, 'context_compressor', None)
        if compressor and getattr(compressor, 'compression_count', 0) > pre_compression_count:
            compressed = True

    if compressed:
        visible_after = visible_messages_for_anchor(session.messages, auto_compression=True)
        session.compression_anchor_visible_idx = (
            max(0, len(visible_after) - 1) if visible_after else None
        )
        session.compression_anchor_message_key = (
            compression_anchor_message_key(visible_after[-1]) if visible_after else None
        )
        session.compression_anchor_summary = compact_summary_text(
            compression_summary_from_messages(session.messages)
            or compression_summary_from_messages(session.context_messages)
        )
        put('compressed', {
            'session_id': session.session_id,
            'message': 'Context auto-compressed to continue the conversation',
            'usage': usage_snapshot(),
        })

    return CompressionSideEffectResult(
        compressed=compressed,
        old_session_id=old_session_id,
        new_session_id=new_session_id,
    )
