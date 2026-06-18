"""Project persistence helpers shared by the session model layer."""

import json
from typing import Callable


def backfill_project_profiles_if_needed(projects: list, *, session_index_file, logger=None) -> bool:
    """Tag legacy unprofiled projects using the session index when possible."""
    untagged = [p for p in projects if not p.get('profile')]
    if not untagged:
        return False

    session_profile_by_project: dict[str, str] = {}
    if session_index_file.exists():
        try:
            entries = json.loads(session_index_file.read_text(encoding='utf-8'))
            untagged_ids = {p['project_id'] for p in untagged if p.get('project_id')}
            for e in entries:
                pid = e.get('project_id')
                if pid in untagged_ids and e.get('profile'):
                    session_profile_by_project.setdefault(pid, e['profile'])
        except Exception:
            if logger:
                logger.debug("Failed to read session index for project profile backfill")

    mutated = False
    for p in untagged:
        inferred = session_profile_by_project.get(p.get('project_id'), 'default')
        p['profile'] = inferred
        mutated = True
    return mutated


def load_projects(
    *,
    projects_file,
    session_index_file,
    migration_lock,
    get_migrated: Callable[[], bool],
    set_migrated: Callable[[bool], None],
    save_projects_fn: Callable[[list], None],
    logger=None,
    _migrate: bool = True,
) -> list:
    """Load projects and run the one-time profile backfill when needed."""
    if not projects_file.exists():
        return []
    try:
        projects = json.loads(projects_file.read_text(encoding='utf-8'))
    except Exception:
        return []
    if _migrate and not get_migrated():
        with migration_lock:
            if get_migrated():
                try:
                    return json.loads(projects_file.read_text(encoding='utf-8'))
                except Exception:
                    return projects
            if backfill_project_profiles_if_needed(
                projects,
                session_index_file=session_index_file,
                logger=logger,
            ):
                try:
                    save_projects_fn(projects)
                    set_migrated(True)
                except Exception:
                    if logger:
                        logger.debug("Failed to persist project profile backfill")
            else:
                set_migrated(True)
    return projects


def save_projects(projects_file, projects) -> None:
    """Write project list to disk."""
    projects_file.write_text(
        json.dumps(projects, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def ensure_cron_project(
    *,
    load_projects_fn: Callable[[], list],
    save_projects_fn: Callable[[list], None],
    cron_lock,
    get_active_profile_name: Callable[[], str | None],
    is_root_profile: Callable[[str], bool],
    make_project_id: Callable[[], str],
    now: Callable[[], float],
    cron_project_name: str,
) -> str:
    """Return the active profile's system cron project, creating it if needed."""
    active = get_active_profile_name() or 'default'
    with cron_lock:
        projects = load_projects_fn()
        for p in projects:
            if p.get('name') != cron_project_name:
                continue
            row_profile = p.get('profile')
            if row_profile == active:
                return p['project_id']
            if is_root_profile(row_profile or 'default') and is_root_profile(active):
                return p['project_id']

        for p in projects:
            if p.get('name') == cron_project_name and not p.get('profile'):
                p['profile'] = active
                save_projects_fn(projects)
                return p['project_id']

        project_id = make_project_id()
        projects.append({
            'project_id': project_id,
            'name': cron_project_name,
            'color': '#6366f1',
            'profile': active,
            'created_at': now(),
        })
        save_projects_fn(projects)
        return project_id
