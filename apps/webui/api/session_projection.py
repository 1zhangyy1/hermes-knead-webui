"""Small projection helpers for session rows and titles."""


def is_streaming_session(active_stream_id, active_stream_ids):
    return bool(active_stream_id and active_stream_id in active_stream_ids)


def message_timestamp(message):
    if not isinstance(message, dict):
        return None
    raw = message.get('_ts') or message.get('timestamp')
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def last_message_timestamp(messages):
    if not isinstance(messages, list):
        return None
    for message in reversed(messages):
        if isinstance(message, dict) and message.get('role') == 'tool':
            continue
        ts = message_timestamp(message)
        if ts:
            return ts
    return None


def message_role(message):
    if not isinstance(message, dict):
        return ''
    return str(message.get('role', '')).strip().lower()


def session_sort_timestamp(session):
    if isinstance(session, dict):
        return session.get('last_message_at') or session.get('updated_at') or 0
    return last_message_timestamp(getattr(session, 'messages', None)) or getattr(session, 'updated_at', 0) or 0


def title_from(messages, fallback: str = 'Untitled'):
    """Derive a session title from the first user message."""
    for message in messages:
        if message.get('role') == 'user':
            content = message.get('content', '')
            if isinstance(content, list):
                content = ' '.join(
                    part.get('text', '')
                    for part in content
                    if isinstance(part, dict) and part.get('type') == 'text'
                )
            text = str(content).strip()
            if text:
                return text[:64]
    return fallback
