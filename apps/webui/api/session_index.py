"""Session index persistence helpers.

This module owns the `_index.json` write/rebuild mechanics.  It deliberately
accepts paths, locks, caches, and a session loader from the caller so existing
tests and profile-specific session stores can continue to patch those values at
the `api.models` boundary.
"""
import json
import logging
import os
import threading
import time


_STALE_TMP_AGE_SECONDS = 3600  # 1 hour

# Serializes index writers so concurrent Session.save() calls cannot race on
# stale baselines while still allowing the caller's session lock to be released
# before disk I/O.
_INDEX_WRITE_LOCK = threading.RLock()


def cleanup_stale_tmp_files(session_dir, *, logger: logging.Logger | None = None) -> None:
    """Best-effort removal of stale ``*.tmp.*`` files from the session dir.

    Only files whose mtime is older than ``_STALE_TMP_AGE_SECONDS`` are removed
    so in-flight writes from a long-running sibling process are not disturbed.
    Errors are logged and swallowed because cleanup must never prevent startup.
    """
    cutoff = time.time() - _STALE_TMP_AGE_SECONDS
    try:
        for p in session_dir.glob('*.tmp.*'):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink(missing_ok=True)
                    if logger:
                        logger.debug("Cleaned up stale tmp file: %s", p.name)
            except OSError:
                pass
    except Exception:
        pass


def index_entry_exists(
    *,
    session_dir,
    sessions,
    sessions_lock,
    session_id: str,
    in_memory_ids=None,
) -> bool:
    """Return True if an index row still has backing session state."""
    if not session_id:
        return False
    if in_memory_ids is None:
        with sessions_lock:
            in_memory_ids = set(sessions.keys())
    if session_id in in_memory_ids:
        return True
    return (session_dir / f'{session_id}.json').exists()


def lookup_index_message_count(index_file, session_id: str):
    """Return indexed message count for a session without loading its JSON."""
    try:
        entries = json.loads(index_file.read_text(encoding='utf-8'))
    except Exception:
        return None
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if entry.get('session_id') != session_id:
            continue
        count = entry.get('message_count')
        if isinstance(count, int) and count >= 0:
            return count
        try:
            count = int(count)
        except (TypeError, ValueError):
            return None
        return count if count >= 0 else None
    return None


def write_session_index(
    *,
    session_dir,
    index_file,
    sessions,
    sessions_lock,
    updates=None,
    load_session,
    logger: logging.Logger | None = None,
) -> None:
    """Update the session index file.

    When *updates* is provided, this patches the existing index with the compact
    entries for those Session objects.  When *updates* is None, a full rebuild is
    performed.  The caller-provided lock protects in-memory snapshots and
    payload construction only; write/flush/fsync/replace runs outside it.
    """
    tmp = index_file.with_suffix(
        f'.tmp.{os.getpid()}.{threading.current_thread().ident}'
    )

    with _INDEX_WRITE_LOCK:
        if updates is None or not index_file.exists():
            cleanup_stale_tmp_files(session_dir, logger=logger)
            entries = []
            for p in session_dir.glob('*.json'):
                if p.name.startswith('_'):
                    continue
                try:
                    s = load_session(p.stem)
                    if s:
                        entries.append(s.compact())
                except Exception:
                    if logger:
                        logger.debug("Failed to load session from %s", p)

            with sessions_lock:
                existing_ids = {e.get('session_id') for e in entries}
                for s in sessions.values():
                    if s.session_id not in existing_ids:
                        entries.append(s.compact())
                entries.sort(key=lambda s: s.get('updated_at', 0), reverse=True)
                payload = json.dumps(entries, ensure_ascii=False, indent=2)

            _atomic_write_index(tmp, index_file, payload)
            return

        fallback = False
        try:
            with sessions_lock:
                existing = json.loads(index_file.read_text(encoding='utf-8'))
                in_memory_ids = set(sessions.keys())

                # Avoid N filesystem exists() checks under the session lock by
                # collecting on-disk IDs once.
                on_disk_ids = {
                    p.stem
                    for p in session_dir.glob('*.json')
                    if not p.name.startswith('_')
                }

                existing = [
                    e for e in existing
                    if (
                        e.get('session_id') in in_memory_ids
                        or e.get('session_id') in on_disk_ids
                    )
                ]

                updated_map = {s.session_id: s.compact() for s in updates}
                existing_ids = {e.get('session_id') for e in existing}
                for sid, entry in updated_map.items():
                    if sid not in existing_ids:
                        existing.append(entry)
                for i, e in enumerate(existing):
                    sid = e.get('session_id')
                    if sid in updated_map:
                        existing[i] = updated_map[sid]
                existing.sort(key=lambda s: s.get('updated_at', 0), reverse=True)
                payload = json.dumps(existing, ensure_ascii=False, indent=2)

            _atomic_write_index(tmp, index_file, payload)
        except Exception:
            fallback = True

    if fallback:
        # Corrupt or missing index: fall back outside the writer lock to avoid
        # recursive deadlock.
        write_session_index(
            session_dir=session_dir,
            index_file=index_file,
            sessions=sessions,
            sessions_lock=sessions_lock,
            updates=None,
            load_session=load_session,
            logger=logger,
        )


def _atomic_write_index(tmp, index_file, payload: str) -> None:
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, index_file)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise
