"""Session JSON serialization and atomic write helpers."""
import json
import os
import threading


def build_session_payload(session, metadata_fields) -> str:
    """Serialize a Session object with metadata fields before messages."""
    meta = {k: getattr(session, k, None) for k in metadata_fields}
    meta['messages'] = session.messages
    meta['tool_calls'] = session.tool_calls
    extra = {
        k: v
        for k, v in session.__dict__.items()
        if k not in metadata_fields
        and k not in ('messages', 'tool_calls')
        and not k.startswith('_')
    }
    return json.dumps({**meta, **extra}, ensure_ascii=False, indent=2)


def write_session_json_with_backup(session_path, payload: str, messages) -> None:
    """Atomically write session JSON after best-effort shrink backup."""
    _write_shrink_backup_if_needed(session_path, messages)
    _atomic_write_text(
        session_path,
        payload,
        tmp_path=session_path.with_suffix(
            f'.tmp.{os.getpid()}.{threading.current_thread().ident}'
        ),
    )


def _write_shrink_backup_if_needed(session_path, messages) -> None:
    try:
        if not session_path.exists():
            return
        existing_text = session_path.read_text(encoding='utf-8')
        try:
            existing = json.loads(existing_text)
            existing_msg_count = len(existing.get('messages') or [])
        except (json.JSONDecodeError, ValueError):
            existing_msg_count = -1  # Preserve historical behavior.
        incoming_msg_count = len(messages or [])
        if existing_msg_count <= incoming_msg_count:
            return
        bak_path = session_path.with_suffix('.json.bak')
        bak_tmp = bak_path.with_suffix(
            f'.bak.tmp.{os.getpid()}.{threading.current_thread().ident}'
        )
        try:
            _atomic_write_text(bak_path, existing_text, tmp_path=bak_tmp)
        except OSError:
            pass
    except OSError:
        pass


def _atomic_write_text(path, payload: str, *, tmp_path) -> None:
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise
