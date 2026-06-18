"""External-agent and CLI session bridge wrappers."""

import os
import time
from pathlib import Path

from api.claude_code_sessions import (
    CLAUDE_CODE_MAX_CONTENT_CHARS,
    CLAUDE_CODE_MAX_FILE_BYTES,
    CLAUDE_CODE_MAX_FILES,
    CLAUDE_CODE_MAX_MESSAGES_PER_FILE,
    CLAUDE_CODE_SOURCE,
    CLAUDE_CODE_SOURCE_LABEL,
    default_projects_dir,
    extract_text,
    get_session_messages as get_claude_code_session_messages_impl,
    get_sessions as get_claude_code_sessions_impl,
    iter_jsonl_files,
    parse_jsonl,
    parse_timestamp,
    session_id_for_path,
    title_from_messages,
)
from api.cli_session_list import (
    clear_cache,
    copy_sessions,
    get_sessions as get_cli_sessions_impl,
    load_uncached as load_cli_sessions_uncached_impl,
    path_cache_key,
    path_stat_cache_key,
    resolve_context as resolve_cli_sessions_context_impl,
    sqlite_file_stat_cache_key,
    ttl_seconds,
)
from api.cli_state_store import (
    count_conversation_rounds as count_cli_conversation_rounds_impl,
    delete_session as delete_cli_session_impl,
    get_session_messages as get_cli_state_session_messages_impl,
    json_loads_if_string,
)


def import_cli_session(
    *,
    session_cls,
    get_workspace,
    session_id: str,
    title: str,
    messages,
    model: str = 'unknown',
    profile=None,
    created_at=None,
    updated_at=None,
    parent_session_id=None,
):
    """Create a new WebUI session populated with CLI/agent messages."""
    session = session_cls(
        session_id=session_id,
        title=title,
        workspace=get_workspace(),
        model=model,
        messages=messages,
        profile=profile,
        created_at=created_at,
        updated_at=updated_at,
        parent_session_id=parent_session_id,
    )
    session.save(touch_updated_at=False)
    return session


def get_claude_code_sessions(
    projects_dir: Path | str | None = None,
    *,
    get_workspace,
    default_projects_dir_fn=default_projects_dir,
    max_files: int = CLAUDE_CODE_MAX_FILES,
    max_file_bytes: int = CLAUDE_CODE_MAX_FILE_BYTES,
) -> list:
    """Read Claude Code JSONL sessions as read-only external-agent rows."""
    return get_claude_code_sessions_impl(
        projects_dir,
        get_workspace=get_workspace,
        default_projects_dir_fn=default_projects_dir_fn,
        max_files=max_files,
        max_file_bytes=max_file_bytes,
    )


def get_claude_code_session_messages(
    sid,
    projects_dir: Path | str | None = None,
    *,
    default_projects_dir_fn=default_projects_dir,
) -> list:
    """Return messages for one read-only Claude Code JSONL session."""
    return get_claude_code_session_messages_impl(
        sid,
        projects_dir,
        default_projects_dir_fn=default_projects_dir_fn,
    )


def resolve_cli_sessions_context(
    *,
    home: Path,
    session_index_file: Path,
    default_projects_dir_fn,
):
    def _active_hermes_home():
        from api.profiles import get_active_hermes_home
        return get_active_hermes_home()

    def _active_profile_name():
        from api.profiles import get_active_profile_name
        return get_active_profile_name()

    return resolve_cli_sessions_context_impl(
        get_active_hermes_home=_active_hermes_home,
        get_active_profile_name=_active_profile_name,
        fallback_hermes_home=Path(os.getenv('HERMES_HOME', str(home / '.hermes'))),
        default_projects_dir=default_projects_dir_fn,
        session_index_file=session_index_file,
    )


def load_cli_sessions_uncached(
    *,
    hermes_home: Path,
    db_path: Path,
    cli_profile,
    get_claude_code_sessions_fn,
    read_importable_agent_session_rows,
    ensure_cron_project,
    is_cron_session,
    load_metadata_only,
    get_workspace,
    logger,
    visible_limit: int,
) -> list:
    return load_cli_sessions_uncached_impl(
        hermes_home=hermes_home,
        db_path=db_path,
        cli_profile=cli_profile,
        get_claude_code_sessions=get_claude_code_sessions_fn,
        read_importable_agent_session_rows=read_importable_agent_session_rows,
        ensure_cron_project=ensure_cron_project,
        is_cron_session=is_cron_session,
        load_metadata_only=load_metadata_only,
        get_workspace=get_workspace,
        logger=logger,
        visible_limit=visible_limit,
    )


def get_cli_sessions(
    *,
    cache: dict,
    cache_lock,
    ttl_seconds_value,
    resolve_context,
    load_uncached,
    logger,
    now=time.monotonic,
) -> list:
    """Read CLI/external-agent sidebar rows, returning [] on bridge errors."""
    hermes_home, db_path, cli_profile, cache_key = resolve_context()
    ttl = ttl_seconds(ttl_seconds_value)

    try:
        return get_cli_sessions_impl(
            cache=cache,
            cache_lock=cache_lock,
            cache_key=cache_key,
            ttl=ttl,
            now=now,
            load_uncached=lambda: load_uncached(hermes_home, db_path, cli_profile),
        )
    except Exception as _cli_err:
        logger.warning(
            "get_cli_sessions() failed — check state.db schema or path (%s): %s",
            db_path, _cli_err,
        )
        return []


def get_cli_session_messages(
    sid,
    *,
    db_path: Path,
    is_continuation_session,
    get_claude_code_session_messages_fn,
) -> list:
    """Read messages for a single CLI/external-agent session."""
    if str(sid or '').startswith(f'{CLAUDE_CODE_SOURCE}_'):
        return get_claude_code_session_messages_fn(sid)
    return get_cli_state_session_messages_impl(
        sid,
        db_path=db_path,
        is_continuation_session=is_continuation_session,
    )


def count_conversation_rounds(sid: str, *, db_path: Path, since: float | None = None) -> int:
    """Count complete user/assistant rounds for a CLI session."""
    return count_cli_conversation_rounds_impl(sid, db_path=db_path, since=since)


def delete_cli_session(sid, *, db_path: Path) -> bool:
    """Delete a CLI session from state.db."""
    return delete_cli_session_impl(sid, db_path=db_path)
