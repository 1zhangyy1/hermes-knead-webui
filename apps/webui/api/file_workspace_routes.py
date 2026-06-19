"""File mutation and workspace mutation helpers for WebUI routes."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable


def handle_file_delete(
    handler,
    body,
    *,
    require_fn: Callable,
    bad_fn: Callable,
    json_response_fn: Callable,
    get_session_fn: Callable,
    safe_resolve_fn: Callable,
    sanitize_error_fn: Callable,
):
    try:
        require_fn(body, "session_id", "path")
    except ValueError as e:
        return bad_fn(handler, str(e))
    try:
        session = get_session_fn(body["session_id"])
    except KeyError:
        return bad_fn(handler, "Session not found", 404)
    try:
        target = safe_resolve_fn(Path(session.workspace), body["path"])
        if not target.exists():
            return bad_fn(handler, "File not found", 404)
        if target.is_dir():
            if not body.get("recursive"):
                return bad_fn(handler, "Set recursive=true to delete directories")
            shutil.rmtree(target)
        else:
            target.unlink()
        return json_response_fn(handler, {"ok": True, "path": body["path"]})
    except (ValueError, PermissionError) as e:
        return bad_fn(handler, sanitize_error_fn(e))


def handle_file_save(
    handler,
    body,
    *,
    require_fn: Callable,
    bad_fn: Callable,
    json_response_fn: Callable,
    get_session_fn: Callable,
    safe_resolve_fn: Callable,
    sanitize_error_fn: Callable,
):
    try:
        require_fn(body, "session_id", "path")
    except ValueError as e:
        return bad_fn(handler, str(e))
    try:
        session = get_session_fn(body["session_id"])
    except KeyError:
        return bad_fn(handler, "Session not found", 404)
    try:
        target = safe_resolve_fn(Path(session.workspace), body["path"])
        if not target.exists():
            return bad_fn(handler, "File not found", 404)
        if target.is_dir():
            return bad_fn(handler, "Cannot save: path is a directory")
        target.write_text(body.get("content", ""), encoding="utf-8")
        return json_response_fn(
            handler,
            {"ok": True, "path": body["path"], "size": target.stat().st_size},
        )
    except (ValueError, PermissionError) as e:
        return bad_fn(handler, sanitize_error_fn(e))


def handle_file_create(
    handler,
    body,
    *,
    require_fn: Callable,
    bad_fn: Callable,
    json_response_fn: Callable,
    get_session_fn: Callable,
    safe_resolve_fn: Callable,
    sanitize_error_fn: Callable,
):
    try:
        require_fn(body, "session_id", "path")
    except ValueError as e:
        return bad_fn(handler, str(e))
    try:
        session = get_session_fn(body["session_id"])
    except KeyError:
        return bad_fn(handler, "Session not found", 404)
    try:
        target = safe_resolve_fn(Path(session.workspace), body["path"])
        if target.exists():
            return bad_fn(handler, "File already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body.get("content", ""), encoding="utf-8")
        return json_response_fn(
            handler,
            {"ok": True, "path": str(target.relative_to(Path(session.workspace)))},
        )
    except (ValueError, PermissionError) as e:
        return bad_fn(handler, sanitize_error_fn(e))


def handle_file_rename(
    handler,
    body,
    *,
    require_fn: Callable,
    bad_fn: Callable,
    json_response_fn: Callable,
    get_session_fn: Callable,
    safe_resolve_fn: Callable,
    sanitize_error_fn: Callable,
):
    try:
        require_fn(body, "session_id", "path", "new_name")
    except ValueError as e:
        return bad_fn(handler, str(e))
    try:
        session = get_session_fn(body["session_id"])
    except KeyError:
        return bad_fn(handler, "Session not found", 404)
    try:
        source = safe_resolve_fn(Path(session.workspace), body["path"])
        if not source.exists():
            return bad_fn(handler, "File not found", 404)
        new_name = body["new_name"].strip()
        if not new_name or "/" in new_name or ".." in new_name:
            return bad_fn(handler, "Invalid file name")
        dest = source.parent / new_name
        if dest.exists():
            return bad_fn(handler, f'A file named "{new_name}" already exists')
        source.rename(dest)
        new_rel = str(dest.relative_to(Path(session.workspace)))
        return json_response_fn(handler, {"ok": True, "old_path": body["path"], "new_path": new_rel})
    except (ValueError, PermissionError, OSError) as e:
        return bad_fn(handler, sanitize_error_fn(e))


def handle_create_dir(
    handler,
    body,
    *,
    require_fn: Callable,
    bad_fn: Callable,
    json_response_fn: Callable,
    get_session_fn: Callable,
    safe_resolve_fn: Callable,
    sanitize_error_fn: Callable,
):
    try:
        require_fn(body, "session_id", "path")
    except ValueError as e:
        return bad_fn(handler, str(e))
    try:
        session = get_session_fn(body["session_id"])
    except KeyError:
        return bad_fn(handler, "Session not found", 404)
    try:
        target = safe_resolve_fn(Path(session.workspace), body["path"])
        if target.exists():
            return bad_fn(handler, "Path already exists")
        target.mkdir(parents=True)
        return json_response_fn(
            handler,
            {"ok": True, "path": str(target.relative_to(Path(session.workspace)))},
        )
    except (ValueError, PermissionError, OSError) as e:
        return bad_fn(handler, sanitize_error_fn(e))


def handle_workspace_add(
    handler,
    body,
    *,
    bad_fn: Callable,
    json_response_fn: Callable,
    load_workspaces_fn: Callable,
    save_workspaces_fn: Callable,
    strip_quotes_fn: Callable,
    is_blocked_system_path_fn: Callable,
    validate_workspace_to_add_fn: Callable,
    sanitize_error_fn: Callable,
):
    path_str = strip_quotes_fn(body.get("path", "").strip())
    name = body.get("name", "").strip()
    auto_create = body.get("create", False)
    if not path_str:
        return bad_fn(handler, "path is required")
    candidate = Path(path_str).expanduser().resolve()
    if is_blocked_system_path_fn(candidate):
        return bad_fn(handler, f"Path points to a system directory: {candidate}")
    if auto_create:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            return bad_fn(handler, f"Could not create directory: {sanitize_error_fn(e)}")
    try:
        path = validate_workspace_to_add_fn(path_str)
    except ValueError as e:
        return bad_fn(handler, str(e))
    workspaces = load_workspaces_fn()
    if any(workspace["path"] == str(path) for workspace in workspaces):
        return bad_fn(handler, "Workspace already in list")
    workspaces.append({"path": str(path), "name": name or path.name})
    save_workspaces_fn(workspaces)
    return json_response_fn(handler, {"ok": True, "workspaces": workspaces})


def handle_workspace_remove(
    handler,
    body,
    *,
    bad_fn: Callable,
    json_response_fn: Callable,
    load_workspaces_fn: Callable,
    save_workspaces_fn: Callable,
):
    path_str = body.get("path", "").strip()
    if not path_str:
        return bad_fn(handler, "path is required")
    workspaces = load_workspaces_fn()
    workspaces = [workspace for workspace in workspaces if workspace["path"] != path_str]
    save_workspaces_fn(workspaces)
    return json_response_fn(handler, {"ok": True, "workspaces": workspaces})


def handle_workspace_rename(
    handler,
    body,
    *,
    bad_fn: Callable,
    json_response_fn: Callable,
    load_workspaces_fn: Callable,
    save_workspaces_fn: Callable,
):
    path_str = body.get("path", "").strip()
    name = body.get("name", "").strip()
    if not path_str or not name:
        return bad_fn(handler, "path and name are required")
    workspaces = load_workspaces_fn()
    for workspace in workspaces:
        if workspace["path"] == path_str:
            workspace["name"] = name
            break
    else:
        return bad_fn(handler, "Workspace not found", 404)
    save_workspaces_fn(workspaces)
    return json_response_fn(handler, {"ok": True, "workspaces": workspaces})


def handle_workspace_reorder(
    handler,
    body,
    *,
    bad_fn: Callable,
    json_response_fn: Callable,
    load_workspaces_fn: Callable,
    save_workspaces_fn: Callable,
):
    paths = body.get("paths", [])
    if not paths or not isinstance(paths, list):
        return bad_fn(handler, "paths is required and must be a list")
    workspaces = load_workspaces_fn()
    by_path = {workspace["path"]: workspace for workspace in workspaces}
    reordered = []
    seen = set()
    for path in paths:
        path = path.strip()
        if path in by_path and path not in seen:
            reordered.append(by_path[path])
            seen.add(path)
    for workspace in workspaces:
        if workspace["path"] not in seen:
            reordered.append(workspace)
    save_workspaces_fn(reordered)
    return json_response_fn(handler, {"ok": True, "workspaces": reordered})
