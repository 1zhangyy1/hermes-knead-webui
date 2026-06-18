"""Build and cache CLI/external-agent session rows for the sidebar."""

import copy
import json
from pathlib import Path
from typing import Callable


def clear_cache(cache: dict, lock) -> None:
    with lock:
        cache.clear()


def copy_sessions(sessions: list) -> list:
    return copy.deepcopy(sessions)


def ttl_seconds(value) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 5.0


def path_cache_key(path) -> str | None:
    if path is None:
        return None
    try:
        return str(Path(path).expanduser().resolve(strict=False))
    except Exception:
        return str(path)


def path_stat_cache_key(path):
    if path is None:
        return None
    try:
        st = Path(path).stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def sqlite_file_stat_cache_key(db_path: Path):
    """Return a cheap invalidation key for a SQLite DB and WAL sidecars."""
    return (
        path_stat_cache_key(db_path),
        path_stat_cache_key(Path(f"{db_path}-wal")),
        path_stat_cache_key(Path(f"{db_path}-shm")),
    )


def resolve_context(
    *,
    get_active_hermes_home: Callable[[], object],
    get_active_profile_name: Callable[[], str | None],
    fallback_hermes_home: Path,
    default_projects_dir: Callable[[], Path | None],
    session_index_file: Path,
) -> tuple[Path, Path, str | None, tuple]:
    """Resolve active CLI home, state.db path, profile, and cache key."""
    try:
        hermes_home = Path(get_active_hermes_home()).expanduser().resolve()
    except Exception:
        hermes_home = fallback_hermes_home.expanduser().resolve()

    try:
        cli_profile = get_active_profile_name()
    except Exception:
        cli_profile = None

    db_path = hermes_home / 'state.db'
    projects_dir = default_projects_dir()
    cache_key = (
        str(hermes_home),
        str(cli_profile or ''),
        str(db_path),
        sqlite_file_stat_cache_key(db_path),
        path_cache_key(projects_dir),
        path_stat_cache_key(projects_dir),
        path_stat_cache_key(session_index_file),
    )
    return hermes_home, db_path, cli_profile, cache_key


def cron_title_from_jobs(hermes_home: Path, sid: str) -> str | None:
    """Return the friendly Cron job name encoded in a cron session id."""
    parts = sid.split('_')
    if len(parts) < 3:
        return None
    job_id = parts[1]
    try:
        jobs_path = hermes_home / 'cron' / 'jobs.json'
        if not jobs_path.exists():
            return None
        jobs_data = json.loads(jobs_path.read_text())
        for job in jobs_data.get('jobs', []):
            if job.get('id') == job_id:
                return job.get('name') or None
    except Exception:
        return None
    return None


def load_uncached(
    *,
    hermes_home: Path,
    db_path: Path,
    cli_profile,
    get_claude_code_sessions: Callable[[], list],
    read_importable_agent_session_rows: Callable[..., list],
    ensure_cron_project: Callable[[], str],
    is_cron_session: Callable[[str, str | None], bool],
    load_metadata_only: Callable[[str], object],
    get_workspace: Callable[[], object],
    logger,
    visible_limit: int,
) -> list:
    """Load CLI sidebar rows from Claude Code files plus state.db rows."""
    cli_sessions = []
    try:
        cli_sessions.extend(get_claude_code_sessions())
    except Exception:
        logger.debug("Claude Code session scan failed", exc_info=True)

    if not db_path.exists():
        return cli_sessions

    cron_pid_cache = [None]

    def cron_pid():
        if cron_pid_cache[0] is None:
            cron_pid_cache[0] = ensure_cron_project()
        return cron_pid_cache[0]

    for row in read_importable_agent_session_rows(
        db_path,
        limit=visible_limit,
        log=logger,
        exclude_sources=None,
    ):
        sid = row['id']
        raw_ts = row['last_activity'] or row['started_at']
        profile = cli_profile

        source = row['source'] or 'cli'
        title = row['title']
        if not title and source == 'cron' and sid.startswith('cron_'):
            title = cron_title_from_jobs(hermes_home, sid) or title

        try:
            webui_meta = load_metadata_only(sid)
            if webui_meta and getattr(webui_meta, 'title', None):
                title = webui_meta.title
        except Exception:
            pass

        display_title = title or f'{source.title()} Session'
        cli_sessions.append({
            'session_id': sid,
            'title': display_title,
            'workspace': str(get_workspace()),
            'model': row['model'] or None,
            'message_count': row['message_count'] or row['actual_message_count'] or 0,
            'created_at': row['started_at'],
            'updated_at': raw_ts,
            'pinned': False,
            'archived': False,
            'project_id': cron_pid() if is_cron_session(sid, source) else None,
            'profile': profile,
            'source_tag': source,
            'raw_source': row.get('raw_source'),
            'user_id': row.get('user_id'),
            'chat_id': row.get('chat_id') or row.get('origin_chat_id'),
            'chat_type': row.get('chat_type'),
            'thread_id': row.get('thread_id'),
            'session_key': row.get('session_key'),
            'platform': row.get('platform'),
            'session_source': row.get('session_source'),
            'source_label': row.get('source_label'),
            'parent_session_id': row.get('parent_session_id'),
            'parent_title': row.get('parent_title'),
            'parent_source': row.get('parent_source'),
            'relationship_type': row.get('relationship_type'),
            '_parent_lineage_root_id': row.get('_parent_lineage_root_id'),
            'end_reason': row.get('end_reason'),
            'actual_message_count': row.get('actual_message_count'),
            'user_message_count': row.get('actual_user_message_count'),
            '_lineage_root_id': row.get('_lineage_root_id'),
            '_lineage_tip_id': row.get('_lineage_tip_id'),
            '_compression_segment_count': row.get('_compression_segment_count'),
            'is_cli_session': True,
        })

    return cli_sessions


def get_sessions(
    *,
    cache: dict,
    cache_lock,
    cache_key,
    ttl: float,
    now: Callable[[], float],
    load_uncached: Callable[[], list],
) -> list:
    """Return cached CLI sessions, deep-copying cache boundaries."""
    if ttl > 0:
        with cache_lock:
            cached = cache.get(cache_key)
            if cached:
                expires_at, cached_sessions = cached
                if expires_at > now():
                    return copy_sessions(cached_sessions)
                cache.pop(cache_key, None)
            sessions = load_uncached()
            cache[cache_key] = (
                now() + ttl,
                copy_sessions(sessions),
            )
            return copy_sessions(sessions)

    return load_uncached()
