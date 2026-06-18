"""Session disk-load helpers.

The public API still lives on `api.models.Session`; these helpers keep the
filesystem and metadata-only load details out of the model class while accepting
caller-provided paths so existing tests can monkeypatch `api.models`.
"""
import json

from api.session_index import lookup_index_message_count
from api.session_metadata import read_session_metadata_payload


_SESSION_ID_CHARS = set('0123456789abcdefghijklmnopqrstuvwxyz_')


def is_valid_session_id(sid) -> bool:
    """Return True for session ids that cannot traverse the filesystem."""
    return bool(sid) and all(c in _SESSION_ID_CHARS for c in sid)


def load_session(session_cls, session_dir, sid):
    """Load a full session JSON sidecar, or None for invalid/missing ids."""
    if not is_valid_session_id(sid):
        return None
    path = session_dir / f'{sid}.json'
    if not path.exists():
        return None
    return session_cls(**json.loads(path.read_text(encoding='utf-8')))


def load_session_metadata_only(session_cls, session_dir, index_file, sid):
    """Load a metadata-only Session instance, falling back to full load."""
    if not is_valid_session_id(sid):
        return None
    path = session_dir / f'{sid}.json'
    if not path.exists():
        return None
    try:
        parsed = read_session_metadata_payload(path)
        if not parsed:
            return load_session(session_cls, session_dir, sid)
        session = session_cls(**parsed)
        session._metadata_message_count = lookup_index_message_count(index_file, sid)
        session._loaded_metadata_only = True
        return session
    except Exception:
        return load_session(session_cls, session_dir, sid)
