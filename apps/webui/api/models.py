"""Hermes Web UI -- Session model and in-memory session store."""
import collections
import logging
import os
import threading
import time
import uuid
from pathlib import Path

import api.config as _cfg
from api.config import (
    SESSION_DIR, SESSION_INDEX_FILE, SESSIONS, SESSIONS_MAX,
    LOCK, STREAMS, STREAMS_LOCK, PROJECTS_FILE, HOME,
    get_effective_default_model, _get_session_agent_lock,
)
from api.workspace import get_last_workspace
from api.agent_sessions import (
    _is_continuation_session,
    read_importable_agent_session_rows,
    read_session_lineage_metadata,
)
from api.session_index import (
    _INDEX_WRITE_LOCK,
    _STALE_TMP_AGE_SECONDS,
    cleanup_stale_tmp_files as _cleanup_session_index_tmp_files,
    index_entry_exists as _session_index_entry_exists,
    lookup_index_message_count as _lookup_session_index_message_count,
    write_session_index as _write_session_index_impl,
)
from api.session_metadata import (
    find_top_level_json_key as _find_top_level_json_key_impl,
    read_metadata_json_prefix as _read_metadata_json_prefix_impl,
)
from api.session_model import Session
from api.session_sidebar import (
    enrich_sidebar_lineage_metadata as _enrich_sidebar_lineage_metadata_impl,
    has_live_sidebar_state as _has_live_sidebar_state_impl,
    hide_from_default_sidebar as _hide_from_default_sidebar_impl,
    prefer_fuller_snapshots_for_sidebar as _prefer_fuller_snapshots_for_sidebar_impl,
    sidebar_lineage_root_id as _sidebar_lineage_root_id_impl,
    sidebar_message_count as _sidebar_message_count_impl,
    sidebar_title_is_generic_webui as _sidebar_title_is_generic_webui_impl,
    strip_sidebar_internal_flags as _strip_sidebar_internal_flags_impl,
)
from api.session_cache import (
    cache_session as _cache_session,
    evict_cached_session_if_same as _evict_cached_session_if_same,
    get_cached_session as _get_cached_session,
)
from api.project_registry import (
    backfill_project_profiles_if_needed as _backfill_project_profiles_impl,
    ensure_cron_project as _ensure_cron_project_impl,
    is_cron_session as _is_cron_session_impl,
    load_projects as _load_projects_impl,
    save_projects as _save_projects_impl,
)
from api.claude_code_sessions import (
    CLAUDE_CODE_MAX_CONTENT_CHARS,
    CLAUDE_CODE_MAX_FILE_BYTES,
    CLAUDE_CODE_MAX_FILES,
    CLAUDE_CODE_MAX_MESSAGES_PER_FILE,
    CLAUDE_CODE_SOURCE,
    CLAUDE_CODE_SOURCE_LABEL,
    default_projects_dir as _default_claude_code_projects_dir_impl,
    extract_text as _extract_claude_code_text_impl,
    get_session_messages as _get_claude_code_session_messages_impl,
    get_sessions as _get_claude_code_sessions_impl,
    iter_jsonl_files as _iter_claude_code_jsonl_files_impl,
    parse_jsonl as _parse_claude_code_jsonl_impl,
    parse_timestamp as _parse_claude_code_timestamp_impl,
    session_id_for_path as _claude_code_session_id_impl,
    title_from_messages as _claude_code_title_impl,
)
from api.cli_state_store import (
    count_conversation_rounds as _count_cli_conversation_rounds_impl,
    delete_session as _delete_cli_session_impl,
    get_session_messages as _get_cli_state_session_messages_impl,
    json_loads_if_string as _json_loads_if_string_impl,
)
from api.cli_session_list import (
    clear_cache as _clear_cli_sessions_cache_impl,
    copy_sessions as _copy_cli_sessions_impl,
    get_sessions as _get_cli_sessions_impl,
    load_uncached as _load_cli_sessions_uncached_impl,
    path_cache_key as _path_cache_key_impl,
    path_stat_cache_key as _path_stat_cache_key_impl,
    resolve_context as _resolve_cli_sessions_context_impl,
    sqlite_file_stat_cache_key as _sqlite_file_stat_cache_key_impl,
    ttl_seconds as _cli_sessions_ttl_seconds_impl,
)
from api.session_repair import (
    append_journaled_partial_output as _append_journaled_partial_output_impl,
    append_recovered_pending_turn as _append_recovered_pending_turn_impl,
    append_recovered_turn_to_context as _append_recovered_turn_to_context_impl,
    apply_core_sync_or_error_marker as _apply_core_sync_or_error_marker_impl,
    find_existing_assistant_for_journal_content as _find_existing_assistant_for_journal_content_impl,
    interrupted_recovery_marker as _interrupted_recovery_marker_impl,
    journal_tool_already_present as _journal_tool_already_present_impl,
    normalize_journal_recovery_text as _normalize_journal_recovery_text_impl,
    repair_stale_pending as _repair_stale_pending_impl,
    run_journal_has_visible_output as _run_journal_has_visible_output_impl,
    truncate_journal_tool_args as _truncate_journal_tool_args_impl,
)
from api.session_projection import (
    is_streaming_session as _is_streaming_session_impl,
    last_message_timestamp as _last_message_timestamp_impl,
    message_role as _message_role_impl,
    message_timestamp as _message_timestamp_impl,
    session_sort_timestamp as _session_sort_timestamp_impl,
    title_from as _title_from_impl,
)
from api.session_paths import (
    active_state_db_path as _active_state_db_path_impl,
    profile_home as _profile_home_impl,
)
from api.session_registry import (
    get_session as _get_session_impl,
    new_session as _new_session_impl,
)
from api.session_listing import (
    all_sessions as _all_sessions_impl,
    diag_stage as _diag_stage_impl,
)

logger = logging.getLogger(__name__)
Session.__module__ = __name__
CLI_VISIBLE_SESSION_LIMIT = 20
_CLI_SESSIONS_CACHE_TTL_SECONDS = 5.0
_CLI_SESSIONS_CACHE_LOCK = threading.Lock()
_CLI_SESSIONS_CACHE = {}

def _cleanup_stale_tmp_files() -> None:
    _cleanup_session_index_tmp_files(SESSION_DIR, logger=logger)


def _index_entry_exists(session_id: str, in_memory_ids=None) -> bool:
    return _session_index_entry_exists(
        session_dir=SESSION_DIR,
        sessions=SESSIONS,
        sessions_lock=LOCK,
        session_id=session_id,
        in_memory_ids=in_memory_ids,
    )


def _write_session_index(updates=None):
    _write_session_index_impl(
        session_dir=SESSION_DIR,
        index_file=SESSION_INDEX_FILE,
        sessions=SESSIONS,
        sessions_lock=LOCK,
        updates=updates,
        load_session=Session.load,
        logger=logger,
    )


def _active_stream_ids():
    with STREAMS_LOCK:
        return set(STREAMS.keys())


def _append_recovered_turn_to_context(session, recovered: dict) -> None:
    _append_recovered_turn_to_context_impl(session, recovered)


def _append_recovered_pending_turn(session, *, timestamp: int | None = None) -> dict | None:
    return _append_recovered_pending_turn_impl(
        session,
        timestamp=timestamp,
        now=time.time,
        append_recovered_turn_to_context=_append_recovered_turn_to_context,
    )


def _is_streaming_session(active_stream_id, active_stream_ids):
    return _is_streaming_session_impl(active_stream_id, active_stream_ids)

def _session_sort_timestamp(session):
    return _session_sort_timestamp_impl(session)


def _message_timestamp(message):
    return _message_timestamp_impl(message)


def _last_message_timestamp(messages):
    return _last_message_timestamp_impl(messages)


def _message_role(message):
    return _message_role_impl(message)


def _find_top_level_json_key(text, key):
    return _find_top_level_json_key_impl(text, key)


def _read_metadata_json_prefix(path, max_prefix_bytes=65536):
    return _read_metadata_json_prefix_impl(path, max_prefix_bytes=max_prefix_bytes)


def _lookup_index_message_count(session_id):
    return _lookup_session_index_message_count(SESSION_INDEX_FILE, session_id)


def _get_profile_home(profile) -> Path:
    """Resolve the hermes agent home directory for the given profile.

    Prefers the profile-specific helper from api.profiles; falls back to the
    HERMES_HOME environment variable or ~/.hermes, expanding ~ correctly.
    """
    return _profile_home_impl(profile, environ=os.environ)


def _interrupted_recovery_marker(*, recovered_output: bool = False) -> dict:
    return _interrupted_recovery_marker_impl(
        recovered_output=recovered_output,
        now=time.time,
    )


def _truncate_journal_tool_args(args, limit: int = 4) -> dict:
    return _truncate_journal_tool_args_impl(args, limit=limit)


def _normalize_journal_recovery_text(value) -> str:
    return _normalize_journal_recovery_text_impl(value)


def _find_existing_assistant_for_journal_content(session, content: str) -> int | None:
    return _find_existing_assistant_for_journal_content_impl(session, content)


def _journal_tool_already_present(session, name: str, preview: str) -> bool:
    return _journal_tool_already_present_impl(session, name, preview)


def _run_journal_has_visible_output(session, stream_id: str | None) -> bool:
    try:
        from api.run_journal import read_run_events
    except Exception:
        return False
    return _run_journal_has_visible_output_impl(
        session,
        stream_id,
        read_run_events=read_run_events,
    )


def _append_journaled_partial_output(
    session,
    stream_id: str | None,
    *,
    dedupe_existing: bool = False,
) -> bool:
    """Recover already-emitted visible output from a dead stream journal.

    This repair path is intentionally conservative: it restores user-visible
    assistant text and tool-card metadata that had already been emitted over
    SSE before the WebUI process died. It does not restore hidden reasoning and
    it does not try to continue execution.
    """
    try:
        from api.run_journal import read_run_events
    except Exception:
        logger.debug(
            "Session %s: failed to read run journal for stream %s",
            getattr(session, 'session_id', '?'),
            stream_id,
            exc_info=True,
        )
        return False
    return _append_journaled_partial_output_impl(
        session,
        stream_id,
        read_run_events=read_run_events,
        logger=logger,
        now=time.time,
        find_existing_assistant_for_journal_content=_find_existing_assistant_for_journal_content,
        journal_tool_already_present=_journal_tool_already_present,
        truncate_journal_tool_args=_truncate_journal_tool_args,
        dedupe_existing=dedupe_existing,
    )


def _apply_core_sync_or_error_marker(
    session,
    core_path,
    stream_id_for_recheck=None,
    *,
    require_stream_dead=True,
    touch_updated_at=True,
) -> bool:
    """Inner repair logic. Must be called with the per-session lock already held.

    Re-checks session state under the lock, then either syncs messages from the
    core transcript (if present and non-empty) or restores the pending user
    message as a recovered user turn and appends an error marker.

    stream_id_for_recheck: when provided, repair bails if session.active_stream_id
    changed (e.g. context compression rotated it).  The cache-miss repair path
    also requires the stream to be absent from active streams; the streaming
    thread's final fallback passes require_stream_dead=False because it runs
    before its own stream is removed from STREAMS.

    Returns True if repair was applied, False if the re-check bailed out.
    Must never raise — caller is responsible for exception handling.
    """
    return _apply_core_sync_or_error_marker_impl(
        session,
        core_path,
        stream_id_for_recheck=stream_id_for_recheck,
        require_stream_dead=require_stream_dead,
        touch_updated_at=touch_updated_at,
        active_stream_ids=_active_stream_ids,
        append_recovered_pending_turn=_append_recovered_pending_turn,
        append_recovered_turn_to_context=_append_recovered_turn_to_context,
        append_journaled_partial_output=_append_journaled_partial_output,
        interrupted_recovery_marker=_interrupted_recovery_marker,
        normalize_journal_recovery_text=_normalize_journal_recovery_text,
        run_journal_has_visible_output=_run_journal_has_visible_output,
        logger=logger,
        now=time.time,
    )


# ── _repair_stale_pending grace period (#1624) ─────────────────────────────
#
# Defense-in-depth against a narrow race between the streaming thread clearing
# pending_user_message and STREAMS.pop(stream_id). Without this guard, any
# fast turn (e.g. command approval) that exits the thread before the on-disk
# pending clear has flushed gets misdiagnosed as a crashed turn, producing a
# spurious "Response interrupted." marker.
#
# 30s covers the worst-case post-loop persistence window: LLM finishing a tool
# batch + lock contention with the checkpoint thread + a multi-MB session.save.
# A legitimately crashed turn whose pending_started_at is < 30s old will not
# repair on the first get_session() call, but WILL repair on the next call
# after the grace period elapses (typically the user's next interaction).
#
# Missing/falsy pending_started_at (legacy sidecars from before that field
# existed, or any path that forgot to set it) is treated as "old enough" so
# repair still recovers them — preserves current behavior for legacy data.
_REPAIR_STALE_PENDING_GRACE_SECONDS = 30


def _repair_stale_pending(session) -> bool:
    """Recover a sidecar stuck with messages=[] and stale pending state.

    Fires only when messages is empty, pending_user_message is set,
    active_stream_id is set, the stream is no longer alive, AND the turn is
    older than _REPAIR_STALE_PENDING_GRACE_SECONDS (#1624).

    Uses a non-blocking lock acquire so a caller that already holds the
    per-session lock (e.g. retry_last, undo_last, cancel_stream) cannot
    deadlock when get_session() triggers this on a cache miss.

    Returns True if repair was applied, False otherwise.
    Must never raise — all errors are caught and logged.
    """
    return _repair_stale_pending_impl(
        session,
        active_stream_ids=_active_stream_ids,
        get_profile_home=_get_profile_home,
        get_session_agent_lock=_get_session_agent_lock,
        apply_core_sync_or_error_marker=_apply_core_sync_or_error_marker,
        logger=logger,
        now=time.time,
        grace_seconds=_REPAIR_STALE_PENDING_GRACE_SECONDS,
    )


def get_session(sid, metadata_only=False):
    """Load a session, optionally with metadata only (skipping the messages array).

    Metadata-only loads intentionally do not populate the full-session cache.
    Otherwise a later full load could return a compact object with an empty
    messages list. Use this when you only need compact() metadata and not the
    actual message history (e.g., for fast sidebar switching).
    """
    return _get_session_impl(
        sid,
        metadata_only=metadata_only,
        sessions=SESSIONS,
        sessions_lock=LOCK,
        sessions_max=SESSIONS_MAX,
        session_cls=Session,
        get_cached_session=_get_cached_session,
        cache_session=_cache_session,
        evict_cached_session_if_same=_evict_cached_session_if_same,
        repair_stale_pending=_repair_stale_pending,
        active_stream_ids=_active_stream_ids,
    )


def new_session(workspace=None, model=None, profile=None, model_provider=None, project_id=None, worktree_info=None):
    """Create a new in-memory session.

    The session lives in the SESSIONS dict only — no disk write happens until
    the first message is appended (#1171 follow-up).  This avoids the
    "ghost Untitled session on disk" pile-up that occurred when users clicked
    New Conversation, reloaded the page, or completed onboarding without ever
    sending a message.  Subsequent code paths that populate state immediately
    (btw / background agent at api/routes.py) call ``s.save()`` themselves
    after setting title/messages, and ``_handle_chat_start`` saves the
    session as soon as the user actually sends a message — both are the
    natural first-write moments for a real session.

    Crash-safety: if the process exits between session creation and first
    message, the session is lost.  Since it had no messages, there is
    nothing to lose.  Worktree-backed sessions are the exception: they are
    saved immediately because creating the session also creates real
    filesystem state that must remain discoverable after restart.

    *profile* — when supplied by the caller (e.g. from the request body sent
    by the active browser tab), it is used directly so that concurrent clients
    on different profiles don't fight over a shared process-global.  If not
    supplied, we fall back to the process-level active profile (the pre-#798
    behaviour, preserved for calls that originate outside a request context).
    """
    def _active_profile_name():
        # Fallback: read process-level global (single-client or startup path)
        from api.profiles import get_active_profile_name
        return get_active_profile_name()

    return _new_session_impl(
        workspace=workspace,
        model=model,
        profile=profile,
        model_provider=model_provider,
        project_id=project_id,
        worktree_info=worktree_info,
        session_cls=Session,
        sessions=SESSIONS,
        sessions_lock=LOCK,
        sessions_max=SESSIONS_MAX,
        cache_session=_cache_session,
        get_active_profile_name=_active_profile_name,
        get_effective_default_model=get_effective_default_model,
        get_last_workspace=get_last_workspace,
    )

def _hide_from_default_sidebar(session: dict) -> bool:
    return _hide_from_default_sidebar_impl(session)


def _sidebar_message_count(session: dict) -> int:
    return _sidebar_message_count_impl(session)


def _sidebar_lineage_root_id(session: dict, sessions_by_id: dict[str, dict]) -> str:
    return _sidebar_lineage_root_id_impl(session, sessions_by_id)


def _has_live_sidebar_state(session: dict) -> bool:
    return _has_live_sidebar_state_impl(session)


def _prefer_fuller_snapshots_for_sidebar(sessions: list[dict]) -> list[dict]:
    return _prefer_fuller_snapshots_for_sidebar_impl(
        sessions,
        sort_timestamp=_session_sort_timestamp,
    )


def _strip_sidebar_internal_flags(sessions: list[dict]) -> None:
    _strip_sidebar_internal_flags_impl(sessions)


def _active_state_db_path() -> Path:
    """Return state.db for the active Hermes profile, degrading to HERMES_HOME."""
    return _active_state_db_path_impl(home=HOME, environ=os.environ)


def _sidebar_title_is_generic_webui(title: str | None) -> bool:
    return _sidebar_title_is_generic_webui_impl(title)


def _enrich_sidebar_lineage_metadata(sessions: list[dict]) -> None:
    _enrich_sidebar_lineage_metadata_impl(
        sessions,
        state_db_path=_active_state_db_path(),
        read_lineage_metadata=read_session_lineage_metadata,
    )


def _diag_stage(diag, name: str) -> None:
    _diag_stage_impl(diag, name)


def all_sessions(diag=None):
    return _all_sessions_impl(
        diag=diag,
        session_index_file=SESSION_INDEX_FILE,
        session_dir=SESSION_DIR,
        sessions=SESSIONS,
        sessions_lock=LOCK,
        session_cls=Session,
        active_stream_ids=_active_stream_ids,
        index_entry_exists=_index_entry_exists,
        write_session_index=_write_session_index,
        is_streaming_session=_is_streaming_session,
        session_sort_timestamp=_session_sort_timestamp,
        prefer_fuller_snapshots_for_sidebar=_prefer_fuller_snapshots_for_sidebar,
        hide_from_default_sidebar=_hide_from_default_sidebar,
        strip_sidebar_internal_flags=_strip_sidebar_internal_flags,
        enrich_sidebar_lineage_metadata=_enrich_sidebar_lineage_metadata,
        logger=logger,
    )


def title_from(messages, fallback: str='Untitled'):
    """Derive a session title from the first user message."""
    return _title_from_impl(messages, fallback=fallback)


# ── Project helpers ──────────────────────────────────────────────────────────

_PROJECTS_MIGRATION_LOCK = threading.Lock()
_projects_migrated = False


def _backfill_project_profiles_if_needed(projects: list) -> bool:
    return _backfill_project_profiles_impl(
        projects,
        session_index_file=SESSION_INDEX_FILE,
        logger=logger,
    )


def _get_projects_migrated() -> bool:
    return _projects_migrated


def _set_projects_migrated(value: bool) -> None:
    global _projects_migrated
    _projects_migrated = bool(value)


def load_projects(*, _migrate: bool = True) -> list:
    return _load_projects_impl(
        projects_file=PROJECTS_FILE,
        session_index_file=SESSION_INDEX_FILE,
        migration_lock=_PROJECTS_MIGRATION_LOCK,
        get_migrated=_get_projects_migrated,
        set_migrated=_set_projects_migrated,
        save_projects_fn=save_projects,
        logger=logger,
        migrate=_migrate,
    )


def save_projects(projects) -> None:
    _save_projects_impl(PROJECTS_FILE, projects)


CRON_PROJECT_NAME = 'Cron Jobs'
_CRON_PROJECT_LOCK = threading.Lock()


def ensure_cron_project() -> str:
    from api.profiles import get_active_profile_name, _is_root_profile

    return _ensure_cron_project_impl(
        load_projects_fn=load_projects,
        save_projects_fn=save_projects,
        cron_lock=_CRON_PROJECT_LOCK,
        get_active_profile_name=get_active_profile_name,
        is_root_profile=_is_root_profile,
        make_project_id=lambda: uuid.uuid4().hex[:12],
        now=time.time,
        cron_project_name=CRON_PROJECT_NAME,
    )


def is_cron_session(session_id: str, source_tag: str = None) -> bool:
    return _is_cron_session_impl(session_id, source_tag=source_tag)


def import_cli_session(
    session_id: str,
    title: str,
    messages,
    model: str='unknown',
    profile=None,
    created_at=None,
    updated_at=None,
    parent_session_id=None,
):
    """Create a new WebUI session populated with CLI/agent messages.

    Preserve parent_session_id from state.db so imported continuation segments
    keep their lineage in the WebUI store and sidebar instead of reappearing as
    detached orphan chats.
    """
    s = Session(
        session_id=session_id,
        title=title,
        workspace=get_last_workspace(),
        model=model,
        messages=messages,
        profile=profile,
        created_at=created_at,
        updated_at=updated_at,
        parent_session_id=parent_session_id,
    )
    s.save(touch_updated_at=False)
    return s


# ── CLI session bridge ──────────────────────────────────────────────────────


def _default_claude_code_projects_dir() -> Path | None:
    """Resolve the Claude Code projects directory without touching real home in tests."""
    return _default_claude_code_projects_dir_impl()


def _claude_code_session_id(path: Path) -> str:
    return _claude_code_session_id_impl(path)


def _parse_claude_code_timestamp(value):
    return _parse_claude_code_timestamp_impl(value)


def _extract_claude_code_text(content) -> str:
    return _extract_claude_code_text_impl(content)


def _parse_claude_code_jsonl(path: Path, *, max_messages: int = CLAUDE_CODE_MAX_MESSAGES_PER_FILE) -> tuple[list[dict], str | None, float | None, float | None]:
    return _parse_claude_code_jsonl_impl(path, max_messages=max_messages)


def _iter_claude_code_jsonl_files(projects_dir: Path | str | None = None, *, max_files: int = CLAUDE_CODE_MAX_FILES, max_file_bytes: int = CLAUDE_CODE_MAX_FILE_BYTES):
    return _iter_claude_code_jsonl_files_impl(
        projects_dir,
        default_projects_dir_fn=_default_claude_code_projects_dir,
        max_files=max_files,
        max_file_bytes=max_file_bytes,
    )


def _claude_code_title(messages: list[dict], summary_title: str | None) -> str:
    return _claude_code_title_impl(messages, summary_title)


def get_claude_code_sessions(projects_dir: Path | str | None = None, *, max_files: int = CLAUDE_CODE_MAX_FILES, max_file_bytes: int = CLAUDE_CODE_MAX_FILE_BYTES) -> list:
    """Read Claude Code JSONL sessions as read-only external-agent rows.

    The bridge is additive and defensive: it skips symlinks, oversized files,
    malformed lines, and per-file errors rather than crashing WebUI session
    listing. Tests pass ``projects_dir`` fixtures so Michael's real ~/.claude is
    never read during test runs.
    """
    return _get_claude_code_sessions_impl(
        projects_dir,
        get_workspace=get_last_workspace,
        default_projects_dir_fn=_default_claude_code_projects_dir,
        max_files=max_files,
        max_file_bytes=max_file_bytes,
    )


def get_claude_code_session_messages(sid, projects_dir: Path | str | None = None) -> list:
    """Return messages for one read-only Claude Code JSONL session."""
    return _get_claude_code_session_messages_impl(
        sid,
        projects_dir,
        default_projects_dir_fn=_default_claude_code_projects_dir,
    )


def clear_cli_sessions_cache() -> None:
    _clear_cli_sessions_cache_impl(_CLI_SESSIONS_CACHE, _CLI_SESSIONS_CACHE_LOCK)


def _copy_cli_sessions(sessions: list) -> list:
    return _copy_cli_sessions_impl(sessions)


def _cli_sessions_cache_ttl_seconds() -> float:
    return _cli_sessions_ttl_seconds_impl(_CLI_SESSIONS_CACHE_TTL_SECONDS)


def _path_cache_key(path) -> str | None:
    return _path_cache_key_impl(path)


def _path_stat_cache_key(path):
    return _path_stat_cache_key_impl(path)


def _sqlite_file_stat_cache_key(db_path: Path):
    """Return a cheap invalidation key for a SQLite DB and WAL sidecars."""
    return _sqlite_file_stat_cache_key_impl(db_path)


def _resolve_cli_sessions_context():
    # Use the active WebUI profile's HERMES_HOME to find state.db.
    # The active profile is determined by what the user has selected in the UI
    # (stored in the server's runtime config). This means:
    #   - default profile  -> ~/.hermes/state.db
    #   - named profile X  -> ~/.hermes/profiles/X/state.db
    # We resolve the active profile's home directory rather than just using
    # HERMES_HOME (which is the server's launch profile, not necessarily the
    # active one after a profile switch).
    def _active_hermes_home():
        from api.profiles import get_active_hermes_home
        return get_active_hermes_home()

    def _active_profile_name():
        from api.profiles import get_active_profile_name
        return get_active_profile_name()

    return _resolve_cli_sessions_context_impl(
        get_active_hermes_home=_active_hermes_home,
        get_active_profile_name=_active_profile_name,
        fallback_hermes_home=Path(os.getenv('HERMES_HOME', str(HOME / '.hermes'))),
        default_projects_dir=_default_claude_code_projects_dir,
        session_index_file=SESSION_INDEX_FILE,
    )


def _load_cli_sessions_uncached(hermes_home: Path, db_path: Path, _cli_profile) -> list:
    return _load_cli_sessions_uncached_impl(
        hermes_home=hermes_home,
        db_path=db_path,
        cli_profile=_cli_profile,
        get_claude_code_sessions=get_claude_code_sessions,
        read_importable_agent_session_rows=read_importable_agent_session_rows,
        ensure_cron_project=ensure_cron_project,
        is_cron_session=is_cron_session,
        load_metadata_only=Session.load_metadata_only,
        get_workspace=get_last_workspace,
        logger=logger,
        visible_limit=CLI_VISIBLE_SESSION_LIMIT,
    )


def get_cli_sessions() -> list:
    """Read CLI sessions from the agent's SQLite store and return them as
    dicts in a format the WebUI sidebar can render alongside local sessions.

    Returns empty list if the SQLite DB is missing or any error occurs -- the
    bridge is purely additive and never crashes the WebUI.
    """
    hermes_home, db_path, cli_profile, cache_key = _resolve_cli_sessions_context()
    ttl = _cli_sessions_cache_ttl_seconds()

    try:
        return _get_cli_sessions_impl(
            cache=_CLI_SESSIONS_CACHE,
            cache_lock=_CLI_SESSIONS_CACHE_LOCK,
            cache_key=cache_key,
            ttl=ttl,
            now=time.monotonic,
            load_uncached=lambda: _load_cli_sessions_uncached(hermes_home, db_path, cli_profile),
        )
    except Exception as _cli_err:
        logger.warning(
            "get_cli_sessions() failed — check state.db schema or path (%s): %s",
            db_path, _cli_err,
        )
        return []


def _json_loads_if_string(value):
    return _json_loads_if_string_impl(value)


def get_cli_session_messages(sid) -> list:
    """Read messages for a single CLI/external-agent session.

    Preserve tool-call/result and reasoning metadata from the agent state.db so
    CLI-origin transcripts render with the same tool cards as WebUI-native
    sessions. When the requested session is the tip of a compression/CLI-close
    continuation chain, return the stitched full transcript across all segments
    in chronological order. Returns empty list on any error.
    """
    if str(sid or '').startswith(f'{CLAUDE_CODE_SOURCE}_'):
        return get_claude_code_session_messages(sid)
    return _get_cli_state_session_messages_impl(
        sid,
        db_path=_active_state_db_path(),
        is_continuation_session=_is_continuation_session,
    )


def count_conversation_rounds(sid: str, since: float | None = None) -> int:
    """Count conversation rounds for a session from state.db.

    A "round" = one user message + one agent reply.  Consecutive user
    messages are merged into a single round so that multi-part questions
    don't inflate the count.

    Parameters
    ----------
    sid : str
        Gateway session ID (e.g. ``20260430_151231_7209a0``).
    since : float | None
        Unix timestamp.  If provided, only messages **after** this
        timestamp are counted.

    Returns
    -------
    int
        Number of complete conversation rounds.
    """
    return _count_cli_conversation_rounds_impl(
        sid,
        db_path=_active_state_db_path(),
        since=since,
    )


CONVERSATION_ROUND_THRESHOLD = 10


def delete_cli_session(sid) -> bool:
    """Delete a CLI session from state.db (messages + session row).
    Returns True if deleted, False if not found or error.
    """
    return _delete_cli_session_impl(sid, db_path=_active_state_db_path())
