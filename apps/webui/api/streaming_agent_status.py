"""Agent lifecycle status bridge for WebUI streaming."""

from __future__ import annotations


COMPRESSION_STATUS_MARKERS = (
    'preflight compression',
    'compressing',
    'compacting context',
    'context too large',
)


def is_compression_status(kind, message) -> bool:
    """Return True when an Agent status event means context compression began."""
    _message = str(message or '').strip()
    _kind = str(kind or '').strip().lower()
    if not _message or _kind != 'lifecycle':
        return False
    _lower = _message.lower()
    return any(marker in _lower for marker in COMPRESSION_STATUS_MARKERS)


def emit_compression_status(kind, message, *, session_id: str, put) -> bool:
    """Emit the WebUI compressing SSE event for compression lifecycle updates."""
    if not is_compression_status(kind, message):
        return False
    put('compressing', {
        'session_id': session_id,
        'message': 'Auto-compressing context to continue...',
    })
    return True


def make_agent_status_callback(*, session_id: str, put):
    """Build the AIAgent status_callback used by the streaming worker."""
    def _agent_status_callback(kind, message):
        emit_compression_status(kind, message, session_id=session_id, put=put)

    return _agent_status_callback

