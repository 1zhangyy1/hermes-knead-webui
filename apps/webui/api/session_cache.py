"""Small LRU cache helpers for in-memory sessions."""


def get_cached_session(sessions, lock, sid):
    """Return a cached session and mark it recently used, or None."""
    with lock:
        if sid in sessions:
            sessions.move_to_end(sid)
            return sessions[sid]
    return None


def cache_session(sessions, lock, sid, session, max_size: int) -> None:
    """Insert/update a cached session and evict least-recently-used entries."""
    with lock:
        sessions[sid] = session
        sessions.move_to_end(sid)
        while len(sessions) > max_size:
            sessions.popitem(last=False)


def evict_cached_session_if_same(sessions, lock, sid, session) -> None:
    """Remove a cached session only if it is still the same object."""
    with lock:
        if sessions.get(sid) is session:
            sessions.pop(sid, None)
