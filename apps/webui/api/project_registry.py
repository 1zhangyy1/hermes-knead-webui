"""Project registry wrappers used by api.models."""

from api.project_store import (
    backfill_project_profiles_if_needed as _backfill_project_profiles_impl,
    ensure_cron_project as _ensure_cron_project_impl,
    load_projects as _load_projects_impl,
    save_projects as _save_projects_impl,
)


def backfill_project_profiles_if_needed(projects: list, *, session_index_file, logger) -> bool:
    """Tag any legacy untagged projects with a sensible profile."""
    return _backfill_project_profiles_impl(
        projects,
        session_index_file=session_index_file,
        logger=logger,
    )


def load_projects(
    *,
    projects_file,
    session_index_file,
    migration_lock,
    get_migrated,
    set_migrated,
    save_projects_fn,
    logger,
    migrate: bool = True,
) -> list:
    """Load project list from disk and run the one-time profile backfill."""
    return _load_projects_impl(
        projects_file=projects_file,
        session_index_file=session_index_file,
        migration_lock=migration_lock,
        get_migrated=get_migrated,
        set_migrated=set_migrated,
        save_projects_fn=save_projects_fn,
        logger=logger,
        _migrate=migrate,
    )


def save_projects(projects_file, projects) -> None:
    """Write project list to disk."""
    _save_projects_impl(projects_file, projects)


def ensure_cron_project(
    *,
    load_projects_fn,
    save_projects_fn,
    cron_lock,
    get_active_profile_name,
    is_root_profile,
    make_project_id,
    now,
    cron_project_name: str,
) -> str:
    """Return the active profile's Cron Jobs project, creating it if needed."""
    return _ensure_cron_project_impl(
        load_projects_fn=load_projects_fn,
        save_projects_fn=save_projects_fn,
        cron_lock=cron_lock,
        get_active_profile_name=get_active_profile_name,
        is_root_profile=is_root_profile,
        make_project_id=make_project_id,
        now=now,
        cron_project_name=cron_project_name,
    )


def is_cron_session(session_id: str, source_tag: str = None) -> bool:
    """Return True if a session originates from a cron job."""
    if source_tag == 'cron':
        return True
    sid = str(session_id or '')
    return sid.startswith('cron_')
