"""Memory lifecycle hooks for completed WebUI streaming turns."""

from __future__ import annotations


def mark_completed_turn_memory_lifecycle(session_id: str, agent, *, logger=None) -> bool:
    """Mark a completed turn as uncommitted; extraction stays a boundary concern."""
    try:
        from api.session_lifecycle import mark_turn_completed

        mark_turn_completed(session_id, agent=agent)
        return True
    except Exception:
        if logger is not None:
            logger.debug("Memory lifecycle mark failed for session %s", session_id, exc_info=True)
        return False
