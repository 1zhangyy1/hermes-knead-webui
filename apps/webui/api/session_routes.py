"""Session utility route handlers for WebUI."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs


def run_journal_status_payload(summary: dict, *, active: bool = False) -> dict:
    terminal = bool(summary.get("terminal"))
    terminal_state = summary.get("terminal_state")
    if not active and not terminal:
        terminal_state = "stale-from-restart"
    return {
        "session_id": summary.get("session_id"),
        "run_id": summary.get("run_id"),
        "last_seq": summary.get("last_seq"),
        "last_event_id": summary.get("last_event_id"),
        "last_event": summary.get("last_event"),
        "terminal": terminal,
        "terminal_state": terminal_state,
    }


def handle_sessions_cleanup(
    handler,
    _body,
    *,
    zero_only: bool = False,
    session_dir: Path,
    session_cls,
    sessions: dict,
    lock,
    session_index_file: Path,
    json_response_fn,
    logger,
) -> bool:
    cleaned = 0
    for path in session_dir.glob("*.json"):
        if path.name.startswith("_"):
            continue
        try:
            session = session_cls.load(path.stem)
            if zero_only:
                should_delete = session and len(session.messages) == 0
            else:
                should_delete = session and session.title == "Untitled" and len(session.messages) == 0
            if should_delete:
                with lock:
                    sessions.pop(path.stem, None)
                path.unlink(missing_ok=True)
                cleaned += 1
        except Exception:
            logger.debug("Failed to clean up session file %s", path)
    if session_index_file.exists():
        session_index_file.unlink(missing_ok=True)
    return json_response_fn(handler, {"ok": True, "cleaned": cleaned})


def handle_session_export(
    handler,
    parsed,
    *,
    get_session_fn,
    redact_session_data_fn,
    bad_response_fn,
) -> bool:
    sid = parse_qs(parsed.query).get("session_id", [""])[0]
    if not sid:
        return bad_response_fn(handler, "session_id is required")
    try:
        session = get_session_fn(sid)
    except KeyError:
        return bad_response_fn(handler, "Session not found", 404)
    safe = redact_session_data_fn(session.__dict__)
    payload = json.dumps(safe, ensure_ascii=False, indent=2)
    encoded = payload.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Disposition", f'attachment; filename="hermes-{sid}.json"')
    handler.send_header("Content-Length", str(len(encoded)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(encoded)
    return True


def handle_sessions_search(
    handler,
    parsed,
    *,
    all_sessions_fn,
    get_session_fn,
    redact_text_fn,
    json_response_fn,
) -> bool:
    qs = parse_qs(parsed.query)
    query = qs.get("q", [""])[0].lower().strip()
    content_search = qs.get("content", ["1"])[0] == "1"
    depth = int(qs.get("depth", ["5"])[0])
    if not query:
        safe_sessions = []
        for session in all_sessions_fn():
            item = dict(session)
            if isinstance(item.get("title"), str):
                item["title"] = redact_text_fn(item["title"])
            safe_sessions.append(item)
        return json_response_fn(handler, {"sessions": safe_sessions})

    results = []
    for session in all_sessions_fn():
        title_match = query in (session.get("title") or "").lower()
        if title_match:
            item = dict(session, match_type="title")
            if isinstance(item.get("title"), str):
                item["title"] = redact_text_fn(item["title"])
            results.append(item)
            continue
        if content_search:
            try:
                full_session = get_session_fn(session["session_id"])
                messages = full_session.messages[:depth] if depth else full_session.messages
                for message in messages:
                    content = message.get("content") or ""
                    if isinstance(content, list):
                        content = " ".join(
                            part.get("text", "")
                            for part in content
                            if isinstance(part, dict) and part.get("type") == "text"
                        )
                    if query in str(content).lower():
                        item = dict(session, match_type="content")
                        if isinstance(item.get("title"), str):
                            item["title"] = redact_text_fn(item["title"])
                        results.append(item)
                        break
            except (KeyError, Exception):
                pass
    return json_response_fn(handler, {"sessions": results, "query": query, "count": len(results)})


def handle_list_dir(
    handler,
    parsed,
    *,
    get_session_fn,
    get_cli_sessions_fn,
    list_dir_fn,
    json_response_fn,
    bad_response_fn,
    sanitize_error_fn,
) -> bool:
    qs = parse_qs(parsed.query)
    sid = qs.get("session_id", [""])[0]
    if not sid:
        return bad_response_fn(handler, "session_id is required")
    try:
        session = get_session_fn(sid)
        workspace = session.workspace
    except KeyError:
        try:
            cli_meta = None
            for cli_session in get_cli_sessions_fn():
                if cli_session["session_id"] == sid:
                    cli_meta = cli_session
                    break
            if not cli_meta:
                return bad_response_fn(handler, "Session not found", 404)
            workspace = cli_meta.get("workspace", "")
        except Exception:
            return bad_response_fn(handler, "Session not found", 404)
    try:
        path = qs.get("path", ["."])[0]
        return json_response_fn(
            handler,
            {
                "entries": list_dir_fn(Path(workspace), path),
                "path": path,
            },
        )
    except (FileNotFoundError, ValueError) as exc:
        return bad_response_fn(handler, sanitize_error_fn(exc), 404)


def handle_session_rename(
    handler,
    body,
    *,
    require_fn,
    bad_response_fn,
    json_response_fn,
    get_session_fn,
    ensure_full_session_fn,
    session_lock_fn,
) -> bool:
    try:
        require_fn(body, "session_id", "title")
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))
    sid = body["session_id"]
    try:
        session = ensure_full_session_fn(sid, get_session_fn(sid))
    except KeyError:
        return bad_response_fn(handler, "Session not found", 404)
    with session_lock_fn(sid):
        session.title = str(body["title"]).strip()[:80] or "Untitled"
        session.save()
    return json_response_fn(handler, {"session": session.compact()})


def handle_personality_set(
    handler,
    body,
    *,
    require_fn,
    bad_response_fn,
    json_response_fn,
    get_session_fn,
    ensure_full_session_fn,
    session_lock_fn,
) -> bool:
    try:
        require_fn(body, "session_id")
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))
    if "name" not in body:
        return bad_response_fn(handler, "Missing required field: name")

    sid = body["session_id"]
    name = str(body["name"] or "").strip()
    try:
        session = ensure_full_session_fn(sid, get_session_fn(sid))
    except KeyError:
        return bad_response_fn(handler, "Session not found", 404)

    prompt = ""
    if name:
        from api.config import get_config, reload_config

        reload_config()
        config = get_config()
        agent_cfg = config.get("agent", {}) if isinstance(config, dict) else {}
        raw_personalities = agent_cfg.get("personalities", {})
        if not isinstance(raw_personalities, dict) or name not in raw_personalities:
            return bad_response_fn(handler, f'Personality "{name}" not found in config.yaml', 404)
        value = raw_personalities[name]
        if isinstance(value, dict):
            parts = [value.get("system_prompt", "") or value.get("prompt", "")]
            if value.get("tone"):
                parts.append(f"Tone: {value['tone']}")
            if value.get("style"):
                parts.append(f"Style: {value['style']}")
            prompt = "\n".join(part for part in parts if part)
        else:
            prompt = str(value)

    with session_lock_fn(sid):
        session.personality = name if name else None
        session.save()
    return json_response_fn(handler, {"ok": True, "personality": session.personality, "prompt": prompt})


def handle_session_toolsets(
    handler,
    body,
    *,
    require_fn,
    bad_response_fn,
    json_response_fn,
    get_session_fn,
    session_lock_fn,
    session_toolsets_from_request_fn,
) -> bool:
    try:
        require_fn(body, "session_id")
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))
    sid = body["session_id"]
    toolsets = body.get("toolsets")
    if toolsets is not None:
        if not isinstance(toolsets, list) or not toolsets:
            return bad_response_fn(handler, "toolsets must be a non-empty list or null")
        if not all(isinstance(item, str) and item for item in toolsets):
            return bad_response_fn(handler, "each toolset must be a non-empty string")
        normalized = session_toolsets_from_request_fn({"toolsets": toolsets})
        if not normalized:
            return bad_response_fn(handler, "no requested toolsets are available")
        toolsets = normalized
    try:
        session = get_session_fn(sid)
    except KeyError:
        return bad_response_fn(handler, "Session not found", 404)
    with session_lock_fn(sid):
        session.enabled_toolsets = toolsets
        session.save()
    return json_response_fn(handler, {"ok": True, "enabled_toolsets": session.enabled_toolsets})


def handle_session_draft(
    handler,
    parsed,
    body,
    *,
    require_fn,
    bad_response_fn,
    json_response_fn,
    get_session_fn,
    session_lock_fn,
) -> bool:
    if getattr(handler, "command", "") == "GET":
        query = parse_qs(parsed.query)
        sid = query.get("session_id", [""])[0] if parsed.query else ""
        if not sid:
            return bad_response_fn(handler, "session_id is required", 400)
        try:
            session = get_session_fn(sid)
        except KeyError:
            return bad_response_fn(handler, "Session not found", 404)
        draft = getattr(session, "composer_draft", {}) or {}
        return json_response_fn(handler, {"draft": draft})

    try:
        require_fn(body, "session_id")
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))
    sid = body["session_id"]
    text = body.get("text")
    files = body.get("files")

    max_draft_text = 50_000
    max_draft_files = 50
    if text is not None and not isinstance(text, str):
        text = ""
    if isinstance(text, str) and len(text) > max_draft_text:
        text = text[:max_draft_text]
    if files is not None and not isinstance(files, list):
        files = []
    if isinstance(files, list) and len(files) > max_draft_files:
        files = files[:max_draft_files]

    try:
        session = get_session_fn(sid)
    except KeyError:
        return bad_response_fn(handler, "Session not found", 404)
    with session_lock_fn(sid):
        draft = getattr(session, "composer_draft", {}) or {}
        if text is not None:
            draft["text"] = text
        if files is not None:
            draft["files"] = files
        session.composer_draft = draft
        session.save()
    return json_response_fn(handler, {"ok": True, "draft": session.composer_draft})


def handle_session_update(
    handler,
    body,
    *,
    require_fn,
    bad_response_fn,
    json_response_fn,
    get_session_fn,
    session_lock_fn,
    resolve_trusted_workspace_fn,
    session_model_state_from_request_fn,
    resolve_context_length_fn,
    set_last_workspace_fn,
    logger,
) -> bool:
    try:
        require_fn(body, "session_id")
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))
    sid = body["session_id"]
    try:
        session = get_session_fn(sid)
    except KeyError:
        return bad_response_fn(handler, "Session not found", 404)
    old_ws = getattr(session, "workspace", "")
    old_model = getattr(session, "model", None)
    old_provider = getattr(session, "model_provider", None)
    try:
        new_ws = str(resolve_trusted_workspace_fn(body.get("workspace", session.workspace)))
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))

    with session_lock_fn(sid):
        session.workspace = new_ws
        if "model" in body or "model_provider" in body:
            model, provider = session_model_state_from_request_fn(
                body.get("model", session.model),
                body.get("model_provider") if "model_provider" in body else None,
                getattr(session, "model_provider", None),
            )
            if model is not None:
                session.model = model
            session.model_provider = provider
            if (
                str(old_model or "") != str(getattr(session, "model", "") or "")
                or str(old_provider or "") != str(getattr(session, "model_provider", "") or "")
            ):
                session.context_length = resolve_context_length_fn(
                    getattr(session, "model", None),
                    getattr(session, "model_provider", None),
                )
                session.threshold_tokens = 0
                session.last_prompt_tokens = 0
        session.save()

    if str(old_ws or "") != str(new_ws or ""):
        try:
            from api.terminal import close_terminal

            close_terminal(sid)
        except Exception:
            logger.debug("Failed to close workspace terminal after workspace update")
    set_last_workspace_fn(new_ws)
    return json_response_fn(handler, {"session": session.compact() | {"messages": session.messages}})
