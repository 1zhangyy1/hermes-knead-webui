"""Project route helpers."""

from __future__ import annotations

import json
import re
import time
import uuid


_PROJECT_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")


def handle_projects_get(
    handler,
    parsed,
    *,
    load_projects_fn,
    profiles_match_fn,
    all_profiles_query_flag_fn,
    json_response_fn,
):
    from api.profiles import get_active_profile_name

    active_profile = get_active_profile_name()
    all_projects = load_projects_fn()
    all_profiles = all_profiles_query_flag_fn(parsed)
    if all_profiles:
        scoped = all_projects
    else:
        scoped = [
            project
            for project in all_projects
            if profiles_match_fn(project.get("profile"), active_profile)
        ]
    return json_response_fn(
        handler,
        {
            "projects": scoped,
            "all_profiles": all_profiles,
            "active_profile": active_profile,
            "other_profile_count": len(all_projects) - len(scoped),
        },
    )


def handle_project_create(
    handler,
    body,
    *,
    require_fn,
    load_projects_fn,
    save_projects_fn,
    json_response_fn,
    bad_response_fn,
):
    try:
        require_fn(body, "name")
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))

    from api.profiles import get_active_profile_name

    name = body["name"].strip()[:128]
    if not name:
        return bad_response_fn(handler, "name required")
    color = body.get("color")
    if color and not _PROJECT_COLOR_RE.match(color):
        return bad_response_fn(handler, "Invalid color format")
    projects = load_projects_fn()
    project = {
        "project_id": uuid.uuid4().hex[:12],
        "name": name,
        "color": color,
        "profile": get_active_profile_name() or "default",
        "created_at": time.time(),
    }
    projects.append(project)
    save_projects_fn(projects)
    return json_response_fn(handler, {"ok": True, "project": project})


def handle_project_rename(
    handler,
    body,
    *,
    require_fn,
    load_projects_fn,
    save_projects_fn,
    profiles_match_fn,
    json_response_fn,
    bad_response_fn,
):
    try:
        require_fn(body, "project_id", "name")
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))

    from api.profiles import get_active_profile_name

    projects = load_projects_fn()
    project = next((p for p in projects if p["project_id"] == body["project_id"]), None)
    if not project:
        return bad_response_fn(handler, "Project not found", 404)
    active_profile = get_active_profile_name()
    if not profiles_match_fn(project.get("profile"), active_profile):
        return bad_response_fn(handler, "Project not found", 404)
    project["name"] = body["name"].strip()[:128]
    if "color" in body:
        color = body["color"]
        if color and not _PROJECT_COLOR_RE.match(color):
            return bad_response_fn(handler, "Invalid color format")
        project["color"] = color
    save_projects_fn(projects)
    return json_response_fn(handler, {"ok": True, "project": project})


def handle_project_delete(
    handler,
    body,
    *,
    require_fn,
    load_projects_fn,
    save_projects_fn,
    profiles_match_fn,
    session_index_file,
    get_session_fn,
    json_response_fn,
    bad_response_fn,
    logger,
):
    try:
        require_fn(body, "project_id")
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))

    from api.profiles import get_active_profile_name

    projects = load_projects_fn()
    project = next((p for p in projects if p["project_id"] == body["project_id"]), None)
    if not project:
        return bad_response_fn(handler, "Project not found", 404)
    active_profile = get_active_profile_name()
    if not profiles_match_fn(project.get("profile"), active_profile):
        return bad_response_fn(handler, "Project not found", 404)

    projects = [p for p in projects if p["project_id"] != body["project_id"]]
    save_projects_fn(projects)
    if session_index_file.exists():
        try:
            index = json.loads(session_index_file.read_text(encoding="utf-8"))
            for entry in index:
                if entry.get("project_id") == body["project_id"]:
                    try:
                        session = get_session_fn(entry["session_id"])
                        session.project_id = None
                        session.save()
                    except Exception:
                        logger.debug("Failed to update session %s", entry.get("session_id"))
        except Exception:
            logger.debug("Failed to load session index for project unlink")
    return json_response_fn(handler, {"ok": True})
