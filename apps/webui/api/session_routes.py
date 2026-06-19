"""Session utility route handlers for WebUI."""

from __future__ import annotations

import copy
import json
import shutil
import time
import uuid
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


def handle_session_new(
    handler,
    body,
    *,
    bad_response_fn,
    json_response_fn,
    resolve_trusted_workspace_fn,
    get_last_workspace_fn,
    session_model_state_from_request_fn,
    session_toolsets_from_request_fn,
    product_task_title_from_request_fn,
    new_session_fn,
    record_product_session_fn,
    logger,
) -> bool:
    try:
        workspace = (
            str(resolve_trusted_workspace_fn(body.get("workspace")))
            if body.get("workspace")
            else None
        )
    except (TypeError, ValueError) as exc:
        return bad_response_fn(handler, str(exc))

    worktree_info = None
    worktree_requested = (
        body.get("worktree") is True
        or str(body.get("worktree")).strip().lower() in {"1", "true", "yes", "on"}
    )
    if worktree_requested:
        try:
            from api.worktrees import create_worktree_for_workspace

            base_workspace = workspace
            if not base_workspace:
                base_workspace = str(resolve_trusted_workspace_fn(get_last_workspace_fn()))
            worktree_info = create_worktree_for_workspace(base_workspace)
            workspace = worktree_info["path"]
        except (TypeError, ValueError) as exc:
            return bad_response_fn(handler, str(exc), status=400)
        except Exception as exc:
            logger.exception("failed to create worktree-backed session")
            return bad_response_fn(handler, f"Failed to create worktree: {exc}", status=500)

    model, model_provider = session_model_state_from_request_fn(
        body.get("model"),
        body.get("model_provider"),
    )

    prev_session_id = body.get("prev_session_id")
    if prev_session_id:
        try:
            from api.config import SESSION_AGENT_CACHE, SESSION_AGENT_CACHE_LOCK
            from api.session_lifecycle import commit_session_memory

            prev_agent = None
            with SESSION_AGENT_CACHE_LOCK:
                cached = SESSION_AGENT_CACHE.get(prev_session_id)
                if cached:
                    prev_agent = cached[0]
            commit_session_memory(prev_session_id, agent=prev_agent)
        except Exception:
            logger.debug("Lifecycle commit for prev_session %s failed", prev_session_id, exc_info=True)

    session = new_session_fn(
        workspace=workspace,
        model=model,
        model_provider=model_provider,
        profile=body.get("profile") or None,
        project_id=body.get("project_id") or None,
        worktree_info=worktree_info,
    )

    session_needs_save = False
    enabled_toolsets = session_toolsets_from_request_fn(body)
    if enabled_toolsets:
        session.enabled_toolsets = enabled_toolsets
        session_needs_save = True

    product_ctx = None
    if body.get("product_id") or body.get("productId"):
        try:
            from api.product_context import product_context_from_request

            product_ctx = product_context_from_request(body, workspace=workspace)
        except ValueError as exc:
            return bad_response_fn(handler, str(exc), status=400)
        if product_ctx:
            product_task_title = product_task_title_from_request_fn(body)
            if product_task_title and product_ctx["scope"] == "product_init":
                session.title = product_task_title
            session.product_id = product_ctx["id"]
            session.product_scope = product_ctx["scope"]
            session.product_intent = product_ctx.get("intent") or ""
            session.product_line = product_ctx.get("line") or "use"
            session_needs_save = True
            if not enabled_toolsets:
                product_toolsets = session_toolsets_from_request_fn(
                    {"toolsets": product_ctx.get("tools") or []}
                )
                if product_toolsets:
                    session.enabled_toolsets = product_toolsets
                    session_needs_save = True
            try:
                next_ui_status = (
                    "generating"
                    if product_ctx["scope"] in {"product_init", "product_builder"}
                    and str(product_ctx.get("ui_mode") or "") != "chat_only"
                    else None
                )
                record_product_session_fn(
                    product_ctx["id"],
                    session.session_id,
                    ui_status=next_ui_status,
                )
            except Exception:
                logger.debug("Failed to bind session %s to product", session.session_id, exc_info=True)

    if session_needs_save:
        try:
            session.save(skip_index=True)
        except Exception:
            logger.debug("Failed to persist new session %s metadata", session.session_id, exc_info=True)

    session_payload = session.compact() | {"messages": session.messages}
    if product_ctx:
        session_payload.update(
            {
                "product_id": product_ctx["id"],
                "product_scope": product_ctx["scope"],
                "product_intent": product_ctx.get("intent") or "",
            }
        )
    return json_response_fn(handler, {"session": session_payload})


def handle_session_delete(
    handler,
    body,
    *,
    bad_response_fn,
    json_response_fn,
    lookup_cli_session_metadata_fn,
    is_messaging_session_id_fn,
    worktree_retained_payload_fn,
    sessions: dict,
    sessions_lock,
    session_index_file: Path,
    session_dir: Path,
    session_agent_locks: dict,
    session_agent_locks_lock,
    logger,
) -> bool:
    sid = body.get("session_id", "")
    if not sid:
        return bad_response_fn(handler, "session_id is required")
    if not all(char in "0123456789abcdefghijklmnopqrstuvwxyz_" for char in sid):
        return bad_response_fn(handler, "Invalid session_id", 400)

    cli_meta_for_delete = lookup_cli_session_metadata_fn(sid)
    if cli_meta_for_delete.get("read_only"):
        return bad_response_fn(handler, "Read-only imported sessions cannot be deleted from WebUI", 400)

    is_messaging_session = is_messaging_session_id_fn(sid)
    worktree_retained = worktree_retained_payload_fn(sid)

    with sessions_lock:
        sessions.pop(sid, None)
    try:
        session_index_file.unlink(missing_ok=True)
    except Exception:
        logger.debug("Failed to unlink session index")

    from api.config import _evict_session_agent

    _evict_session_agent(sid)
    try:
        path = (session_dir / f"{sid}.json").resolve()
        path.relative_to(session_dir.resolve())
    except Exception:
        return bad_response_fn(handler, "Invalid session_id", 400)

    try:
        path.unlink(missing_ok=True)
        path.with_suffix(".json.bak").unlink(missing_ok=True)
    except Exception:
        logger.debug("Failed to unlink session file %s", path)

    try:
        from api.upload import _session_attachment_dir

        shutil.rmtree(_session_attachment_dir(sid), ignore_errors=True)
    except Exception:
        logger.debug("Failed to clean attachment dir for deleted session %s", sid)

    with session_agent_locks_lock:
        session_agent_locks.pop(sid, None)

    try:
        from api.terminal import close_terminal

        close_terminal(sid)
    except Exception:
        logger.debug("Failed to close workspace terminal for deleted session %s", sid)

    if not is_messaging_session:
        try:
            from api.models import delete_cli_session

            delete_cli_session(sid)
        except Exception:
            logger.debug("Failed to delete CLI session %s", sid)

    return json_response_fn(handler, {"ok": True, **worktree_retained})


def handle_session_duplicate(
    handler,
    body,
    *,
    bad_response_fn,
    json_response_fn,
    session_cls,
    sessions: dict,
    sessions_lock,
    sessions_max: int,
) -> bool:
    try:
        sid = body.get("session_id")
        if not sid:
            return bad_response_fn(handler, "session_id is required")

        session = session_cls.load(sid)
        if not session:
            return bad_response_fn(handler, "Session not found", status=404)

        copied_session = session_cls(
            session_id=uuid.uuid4().hex[:12],
            title=(session.title or "Untitled") + " (copy)",
            workspace=session.workspace,
            model=session.model,
            model_provider=session.model_provider,
            messages=copy.deepcopy(session.messages),
            tool_calls=copy.deepcopy(session.tool_calls),
            pinned=False,
            archived=False,
            project_id=session.project_id,
            profile=session.profile,
            input_tokens=session.input_tokens,
            output_tokens=session.output_tokens,
            estimated_cost=session.estimated_cost,
            personality=session.personality,
            enabled_toolsets=getattr(session, "enabled_toolsets", None),
            context_length=getattr(session, "context_length", None),
            threshold_tokens=getattr(session, "threshold_tokens", None),
            created_at=time.time(),
            updated_at=time.time(),
        )

        with sessions_lock:
            sessions[copied_session.session_id] = copied_session
            sessions.move_to_end(copied_session.session_id)
            while len(sessions) > sessions_max:
                sessions.popitem(last=False)

        copied_session.save()
        return json_response_fn(
            handler,
            {"session": copied_session.compact() | {"messages": copied_session.messages}},
        )
    except Exception as exc:
        return bad_response_fn(handler, str(exc))


def handle_session_branch(
    handler,
    body,
    *,
    require_fn,
    bad_response_fn,
    json_response_fn,
    get_session_fn,
    session_cls,
    sessions: dict,
    sessions_lock,
    sessions_max: int,
    lookup_cli_session_metadata_fn,
    session_requires_cli_metadata_lookup_fn,
    is_messaging_session_record_fn,
    get_cli_session_messages_fn,
    merged_session_messages_for_display_fn,
) -> bool:
    try:
        require_fn(body, "session_id")
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))
    if not isinstance(body["session_id"], str):
        return bad_response_fn(handler, "session_id must be a string")
    try:
        source = get_session_fn(body["session_id"])
    except KeyError:
        return bad_response_fn(handler, "Session not found", 404)

    keep_count = body.get("keep_count")
    if keep_count is not None:
        try:
            keep_count = int(keep_count)
        except (ValueError, TypeError):
            return bad_response_fn(handler, "keep_count must be an integer")
        if keep_count < 0:
            return bad_response_fn(handler, "keep_count must be non-negative")

    custom_title = body.get("title")
    if custom_title:
        custom_title = str(custom_title).strip()[:80] or None

    try:
        source.save()
    except Exception:
        pass
    cli_meta = (
        lookup_cli_session_metadata_fn(source.session_id)
        if session_requires_cli_metadata_lookup_fn(source)
        else {}
    )
    is_messaging_session = is_messaging_session_record_fn(source) or is_messaging_session_record_fn(cli_meta)
    cli_messages = get_cli_session_messages_fn(source.session_id) if is_messaging_session else []
    source_messages = (
        merged_session_messages_for_display_fn(source, cli_messages)
        if is_messaging_session and cli_messages
        else list(source.messages or [])
    )
    if keep_count is not None:
        forked_messages = source_messages[:keep_count]
    else:
        forked_messages = list(source_messages)

    if custom_title:
        branch_title = custom_title
    else:
        source_title = source.title or "Untitled"
        branch_title = f"{source_title} (fork)"

    branch = session_cls(
        workspace=source.workspace,
        model=source.model,
        profile=getattr(source, "profile", None),
        title=branch_title,
        messages=forked_messages,
        parent_session_id=source.session_id,
        session_source="fork",
    )
    with sessions_lock:
        sessions[branch.session_id] = branch
        sessions.move_to_end(branch.session_id)
        while len(sessions) > sessions_max:
            sessions.popitem(last=False)

    if forked_messages:
        branch.save()

    return json_response_fn(
        handler,
        {
            "session_id": branch.session_id,
            "title": branch_title,
            "parent_session_id": source.session_id,
        },
    )


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


def handle_session_pin(
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
    try:
        session = get_session_fn(body["session_id"])
        session = ensure_full_session_fn(body["session_id"], session)
    except KeyError:
        return bad_response_fn(handler, "Session not found", 404)
    with session_lock_fn(body["session_id"]):
        session.pinned = bool(body.get("pinned", True))
        session.save()
    return json_response_fn(handler, {"ok": True, "session": session.compact()})


def handle_session_archive(
    handler,
    body,
    *,
    require_fn,
    bad_response_fn,
    json_response_fn,
    get_session_fn,
    ensure_full_session_fn,
    session_lock_fn,
    session_cls,
    sessions,
    sessions_lock,
    lookup_cli_session_metadata_fn,
    is_messaging_session_record_fn,
    get_cli_session_messages_fn,
    import_cli_session_fn,
    title_from_fn,
    get_last_workspace_fn,
    worktree_retained_payload_fn,
) -> bool:
    try:
        require_fn(body, "session_id")
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))
    sid = body["session_id"]
    try:
        session = get_session_fn(sid)
        session = ensure_full_session_fn(sid, session)
    except KeyError:
        cli_meta = lookup_cli_session_metadata_fn(sid)
        if not cli_meta:
            return bad_response_fn(handler, "Session not found", 404)
        if cli_meta.get("read_only"):
            return bad_response_fn(handler, "Read-only imported sessions cannot be archived from WebUI", 400)
        if is_messaging_session_record_fn(cli_meta):
            session = session_cls(
                session_id=sid,
                title=cli_meta.get("title") or title_from_fn(get_cli_session_messages_fn(sid), "CLI Session"),
                workspace=get_last_workspace_fn(),
                messages=[],
                model=cli_meta.get("model") or "unknown",
                created_at=cli_meta.get("created_at"),
                updated_at=cli_meta.get("updated_at"),
            )
            session.is_cli_session = True
            session.source_tag = cli_meta.get("source_tag")
            session.raw_source = cli_meta.get("raw_source") or cli_meta.get("source_tag")
            session.session_source = cli_meta.get("session_source")
            session.source_label = cli_meta.get("source_label")
            session.user_id = cli_meta.get("user_id")
            session.chat_id = cli_meta.get("chat_id")
            session.chat_type = cli_meta.get("chat_type")
            session.thread_id = cli_meta.get("thread_id")
            session.session_key = cli_meta.get("session_key")
            session.platform = cli_meta.get("platform")
            session.save(touch_updated_at=False)
        else:
            messages = get_cli_session_messages_fn(sid)
            if not messages:
                return bad_response_fn(handler, "Session not found", 404)
            session = import_cli_session_fn(
                sid,
                cli_meta.get("title") or title_from_fn(messages, "CLI Session"),
                messages,
                cli_meta.get("model") or "unknown",
                profile=cli_meta.get("profile"),
                created_at=cli_meta.get("created_at"),
                updated_at=cli_meta.get("updated_at"),
            )
            session.is_cli_session = True
            session.source_tag = cli_meta.get("source_tag")
            session.raw_source = cli_meta.get("raw_source") or cli_meta.get("source_tag")
            session.session_source = cli_meta.get("session_source")
            session.source_label = cli_meta.get("source_label")
            session.user_id = cli_meta.get("user_id")
            session.chat_id = cli_meta.get("chat_id")
            session.chat_type = cli_meta.get("chat_type")
            session.thread_id = cli_meta.get("thread_id")
            session.session_key = cli_meta.get("session_key")
            session.platform = cli_meta.get("platform")
    if getattr(session, "_loaded_metadata_only", False):
        loaded = session_cls.load(sid)
        if loaded is None:
            return bad_response_fn(handler, "Session not found", 404)
        session = loaded
        with sessions_lock:
            sessions[sid] = session
    with session_lock_fn(sid):
        session.archived = bool(body.get("archived", True))
        session.save(touch_updated_at=False)
    return json_response_fn(
        handler,
        {"ok": True, "session": session.compact(), **worktree_retained_payload_fn(session)},
    )


def handle_session_move(
    handler,
    body,
    *,
    require_fn,
    bad_response_fn,
    json_response_fn,
    get_session_fn,
    session_lock_fn,
    load_projects_fn,
    profiles_match_fn,
) -> bool:
    try:
        require_fn(body, "session_id")
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))
    try:
        session = get_session_fn(body["session_id"])
    except KeyError:
        return bad_response_fn(handler, "Session not found", 404)

    target_pid = body.get("project_id") or None
    if target_pid:
        from api.profiles import get_active_profile_name

        active_profile = get_active_profile_name()
        target = next(
            (project for project in load_projects_fn() if project["project_id"] == target_pid),
            None,
        )
        if not target:
            return bad_response_fn(handler, "Project not found", 404)
        if not profiles_match_fn(target.get("profile"), active_profile):
            return bad_response_fn(handler, "Project not found", 404)
    with session_lock_fn(body["session_id"]):
        session.project_id = target_pid
        session.save()
    return json_response_fn(handler, {"ok": True, "session": session.compact()})


def handle_session_clear(
    handler,
    body,
    *,
    require_fn,
    bad_response_fn,
    json_response_fn,
    get_session_fn,
    session_lock_fn,
    evict_session_agent_fn,
) -> bool:
    try:
        require_fn(body, "session_id")
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))
    try:
        session = get_session_fn(body["session_id"])
    except KeyError:
        return bad_response_fn(handler, "Session not found", 404)
    sid = body["session_id"]
    with session_lock_fn(sid):
        session.messages = []
        session.tool_calls = []
        session.title = "Untitled"
        session.save()
    evict_session_agent_fn(sid)
    return json_response_fn(handler, {"ok": True, "session": session.compact()})


def handle_session_truncate(
    handler,
    body,
    *,
    require_fn,
    bad_response_fn,
    json_response_fn,
    get_session_fn,
    session_lock_fn,
) -> bool:
    try:
        require_fn(body, "session_id")
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))
    if body.get("keep_count") is None:
        return bad_response_fn(handler, "Missing required field(s): keep_count")
    try:
        session = get_session_fn(body["session_id"])
    except KeyError:
        return bad_response_fn(handler, "Session not found", 404)
    keep = int(body["keep_count"])
    with session_lock_fn(body["session_id"]):
        session.messages = session.messages[:keep]
        session.save()
    return json_response_fn(
        handler,
        {"ok": True, "session": session.compact() | {"messages": session.messages}},
    )


def handle_session_retry(handler, body, *, require_fn, bad_response_fn, json_response_fn) -> bool:
    try:
        require_fn(body, "session_id")
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))
    try:
        from api.session_ops import retry_last

        result = retry_last(body["session_id"])
        return json_response_fn(handler, {"ok": True, **result})
    except KeyError:
        return bad_response_fn(handler, "Session not found", 404)
    except ValueError as exc:
        return json_response_fn(handler, {"error": str(exc)})


def handle_session_undo(handler, body, *, require_fn, bad_response_fn, json_response_fn) -> bool:
    try:
        require_fn(body, "session_id")
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))
    try:
        from api.session_ops import undo_last

        result = undo_last(body["session_id"])
        return json_response_fn(handler, {"ok": True, **result})
    except KeyError:
        return bad_response_fn(handler, "Session not found", 404)
    except ValueError as exc:
        return json_response_fn(handler, {"error": str(exc)})


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


def handle_session_worktree_status(
    handler,
    parsed,
    *,
    get_session_fn,
    bad_response_fn,
    json_response_fn,
    sanitize_error_fn,
    logger,
) -> bool:
    query = parse_qs(parsed.query)
    sid = query.get("session_id", [""])[0]
    if not sid:
        return bad_response_fn(handler, "session_id is required", status=400)
    try:
        session = get_session_fn(sid, metadata_only=True)
    except KeyError:
        return bad_response_fn(handler, "Session not found", status=404)
    try:
        from api.worktrees import worktree_status_for_session

        return json_response_fn(handler, {"status": worktree_status_for_session(session)})
    except ValueError as exc:
        return bad_response_fn(handler, str(exc), status=400)
    except Exception as exc:
        logger.exception("failed to read worktree status for session %s", sid)
        return bad_response_fn(handler, sanitize_error_fn(exc), status=500)


def handle_session_worktree_remove(
    handler,
    body,
    *,
    bad_response_fn,
    json_response_fn,
    get_session_fn,
    sanitize_error_fn,
    logger,
) -> bool:
    sid = body.get("session_id", "")
    if not sid or not isinstance(sid, str) or not sid.strip():
        return bad_response_fn(handler, "session_id must be a non-empty string", status=400)
    sid = sid.strip()
    if not all(char in "0123456789abcdefghijklmnopqrstuvwxyz_" for char in sid):
        return bad_response_fn(handler, "Invalid session_id", 400)
    try:
        session = get_session_fn(sid, metadata_only=True)
    except KeyError:
        return bad_response_fn(handler, "Session not found", status=404)
    force = bool(body.get("force", False))
    try:
        from api.worktrees import remove_worktree_for_session

        result = remove_worktree_for_session(session, force=force)
        return json_response_fn(handler, result)
    except ValueError as exc:
        return bad_response_fn(handler, str(exc), status=400)
    except Exception as exc:
        logger.exception("failed to remove worktree for session %s", sid)
        return bad_response_fn(handler, sanitize_error_fn(exc), status=500)


def handle_session_status(
    handler,
    parsed,
    *,
    get_session_fn,
    clear_stale_stream_state_fn,
    bad_response_fn,
    json_response_fn,
) -> bool:
    sid = parse_qs(parsed.query).get("session_id", [""])[0]
    if not sid:
        return bad_response_fn(handler, "Missing session_id")
    try:
        from api.session_ops import session_status

        clear_stale_stream_state_fn(get_session_fn(sid, metadata_only=True))
        return json_response_fn(handler, session_status(sid))
    except KeyError:
        return bad_response_fn(handler, "Session not found", 404)


def handle_session_yolo_get(
    handler,
    parsed,
    *,
    is_session_yolo_enabled_fn,
    bad_response_fn,
    json_response_fn,
) -> bool:
    sid = parse_qs(parsed.query).get("session_id", [""])[0]
    if not sid:
        return bad_response_fn(handler, "Missing session_id")
    return json_response_fn(handler, {"yolo_enabled": is_session_yolo_enabled_fn(sid)})


def handle_session_usage(handler, parsed, *, bad_response_fn, json_response_fn) -> bool:
    sid = parse_qs(parsed.query).get("session_id", [""])[0]
    if not sid:
        return bad_response_fn(handler, "Missing session_id")
    try:
        from api.session_ops import session_usage

        return json_response_fn(handler, session_usage(sid))
    except KeyError:
        return bad_response_fn(handler, "Session not found", 404)


def handle_session_yolo_post(
    handler,
    body,
    *,
    require_fn,
    bad_response_fn,
    json_response_fn,
    enable_session_yolo_fn,
    disable_session_yolo_fn,
    resolve_gateway_approval_fn,
) -> bool:
    try:
        require_fn(body, "session_id")
    except ValueError as exc:
        return bad_response_fn(handler, str(exc))
    sid = body["session_id"]
    enabled = bool(body.get("enabled", True))
    if enabled:
        enable_session_yolo_fn(sid)
        try:
            from tools.approval import _pending as _p, _lock as _l

            with _l:
                _p.pop(sid, None)
        except Exception:
            pass
        resolve_gateway_approval_fn(sid, "once", resolve_all=True)
    else:
        disable_session_yolo_fn(sid)
    return json_response_fn(handler, {"ok": True, "yolo_enabled": enabled})
